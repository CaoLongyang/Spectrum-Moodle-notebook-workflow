#!/usr/bin/env python3
"""让 NotebookLM 云端和本地 Week 文件夹保持一致，并按"周"生成 quiz 和闪卡。

不再依赖任何 JSON 状态文件：每次运行都是"看本地有什么、看云端有什么、把差的补齐"。

做法：
- 只看 UM_Courses/<课程>/ 下两类文件夹里的文件（其他文件夹如 Introduction、General 不管）：
    * 名字里带 week 的（不分大小写，如 Week 3、WEEK 3、week 3 (F2F)）：按周生成 quiz 和闪卡
    * 名字里带 exam 的（如 EXAM）：只上传，不生成 quiz 和闪卡，留给你自己处理
- 每门课一个笔记本（名字 = 课程代码，如 WIA2001），按名字自动找到，没有就新建
- 云端来源的标题格式：  文件名 [#哈希前6位]，哈希是文件内容算的，靠它判断是不是同一个文件
  （所以请不要在网页上手动改来源的标题）

第一步 同步来源（云端以本地为准）
  - 本地有、云端没有的 -> 上传
  - 云端有、本地没有的（包括没有哈希标签的、重复的、处理失败的）-> 删除
第二步 quiz / 闪卡
  - 每个 quiz / 闪卡都带有生成时用的来源。它的来源集合必须和"这一周本地文件"完全一致，
    否则就是旧版本（删了文件、改了文件、新增了文件都会导致不一致）-> 删掉并重新生成
  - 这一周缺 quiz 或闪卡 -> 生成；quiz 和闪卡同时生成，名字为 "Week N - Quiz/Flashcards"
  - 每次运行结束时检查名字，被 NotebookLM 改掉的会改回来
  - 只处理 quiz 和闪卡；你自己手动生成的不会被动，用到 EXAM 来源的更是一律不碰
  - 生成每周的 quiz/闪卡时只用那一周的文件，不会混入 EXAM 的内容
- 处理顺序：先做所有课的最小周，再做所有课的下一周，依此类推
- 被限速时等 5 秒再试一次，还不行就终止；额度恢复后重新运行会自动接着做
- 有删除操作时，会先列出清单并问你确认（加 --yes 跳过）；--dry-run 只看计划不执行

前提：已运行 spectrum_download.py 和 notebooklm login，
并在 prompts/quiz.txt、prompts/flashcards.txt 里放好提示词。
名字里带 GKU 的课程会被整个跳过；WIX2001 的 Lecture Notes 已由 spectrum_download.py
按 L1/L2/... 分到了 Week N 文件夹里，这里不需要特殊处理。
"""
import argparse
import asyncio
import hashlib
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from notebooklm import NotebookLMClient, RateLimitError

# ============ 配置 ============
OUT_DIR = Path("UM_Courses")        # 和 spectrum_download.py 一致
PROMPT_DIR = Path("prompts")
EXCLUDE_COURSES = ["GKU"]           # 文件夹名里包含这些字样的课程会被跳过（不分大小写）
LOCAL_EXTENSIONS = (".pdf", ".ppt", ".pptx", ".docx")
HASH_LEN = 6                        # 标题里的哈希取前几位（同一门课里撞了会报错提醒你调大）
UPLOAD_GAP = 1.5                    # 每次上传之间的间隔（秒）
RATE_WAIT = 5                       # 被限速后等待多久再试一次（秒）；再失败就终止
GEN_TIMEOUT = 900                   # 单个生成任务最长等待（秒）
NAME_CHECK_DELAY = 5                # 生成完后等多久再检查名字（秒）
# ==============================

WEEK_RE = re.compile(r"week\s*0*(\d+)", re.IGNORECASE)   # 文件夹名里任意位置出现 week + 数字
EXAM_RE = re.compile(r"exam", re.IGNORECASE)               # 文件夹名里出现 exam
TAG_RE = re.compile(rf"\[#([0-9a-f]{{{HASH_LEN}}})\]\s*$")
OUR_TITLE_RE = re.compile(r"^Week (\d+) - (Quiz|Flashcards)$")
KINDS = ("quiz", "flashcards")
LABELS = {"quiz": "Quiz", "flashcards": "Flashcards"}
logging.getLogger("notebooklm").setLevel(logging.CRITICAL)  # 隐藏库自带的冗长报错


# ==================== 数据结构 ====================

@dataclass(frozen=True)
class LocalFile:
    path: Path
    week: int | None  # None = EXAM 文件夹里的文件（只上传，不生成）
    digest: str       # 完整哈希（SHA-1）

    @property
    def tag(self):
        return self.digest[:HASH_LEN]

    @property
    def title(self):
        """上传到云端时用的标题：文件名 [#哈希]"""
        return f"{self.path.name} [#{self.tag}]"

    @property
    def is_exam(self):
        return self.week is None


@dataclass
class CoursePlan:
    """某门课"本地 vs 云端"的差异，以及要做的事。"""
    course: str                  # 课程文件夹名，如 129_WIA2001
    files: list                  # 本地文件（Week 和 EXAM 文件夹里的）
    want: dict = field(default_factory=dict)            # 周 -> 这一周应有的来源哈希集合
    exam_tags: frozenset = frozenset()                  # 只出现在 EXAM 里的文件的哈希
    nb_id: str = None            # 云端笔记本 id（None = 还没有，需要新建）
    source_by_tag: dict = field(default_factory=dict)   # 哈希 -> 云端来源 id（保留的）
    drop_sources: list = field(default_factory=list)    # 要删的云端来源
    upload: list = field(default_factory=list)          # 要上传的本地文件
    drop_artifacts: list = field(default_factory=list)  # 要删的旧 quiz/闪卡
    titles: dict = field(default_factory=dict)          # 生成物 id -> 应有的名字
    missing: dict = field(default_factory=dict)         # 周 -> 要生成的种类列表

    @property
    def code(self):
        return re.sub(r"^\d+_", "", self.course)  # 129_WIA2001 -> WIA2001

    @property
    def has_work(self):
        return bool(self.nb_id is None or self.drop_sources or self.upload
                    or self.drop_artifacts or self.missing)

    @property
    def destructive(self):
        return bool(self.drop_sources or self.drop_artifacts)


class Outcome(Enum):
    OK = "ok"
    FAIL = "fail"
    LIMIT = "limit"  # 被限速，重试后仍失败


# ==================== 本地：扫描 Week 文件夹 ====================

def file_digest(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_local():
    """返回 ({课程文件夹名: [LocalFile]}, [不支持的文件])。
    只看名字里带 week 的文件夹（按周）和带 exam 的文件夹（只上传）。"""
    courses, unsupported = {}, []
    if not OUT_DIR.exists():
        return courses, unsupported
    for p in sorted(OUT_DIR.rglob("*")):
        parts = p.relative_to(OUT_DIR).parts  # 课程 / 章节 / ... / 文件
        if len(parts) < 3 or not p.is_file():
            continue
        if p.name.startswith(("~", ".")) or p.suffix.lower() == ".part":
            continue
        if any(x.lower() in parts[0].lower() for x in EXCLUDE_COURSES):
            continue
        week = WEEK_RE.search(parts[1])
        if not week and not EXAM_RE.search(parts[1]):
            continue  # Week 优先：像 "Week 7 - Exam Revision" 这样的按周处理
        if p.suffix.lower() not in LOCAL_EXTENSIONS:
            unsupported.append(p)
            continue
        courses.setdefault(parts[0], []).append(
            LocalFile(p, int(week.group(1)) if week else None, file_digest(p)))
    return courses, unsupported


def check_collisions(course, files):
    """同一门课里不同文件的哈希前缀撞了，就没法区分，直接报错。"""
    seen = {}
    for f in files:
        if seen.setdefault(f.tag, f.digest) != f.digest:
            sys.exit(f"❌ {course} 里有两个不同的文件哈希前 {HASH_LEN} 位相同（{f.path.name}），"
                     f"请把 HASH_LEN 调大后重试。")


def read_prompt(kind):
    path = PROMPT_DIR / f"{kind}.txt"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    print(f"⚠️  没找到提示词 {path}，{kind} 将使用 NotebookLM 默认设置。")
    return None


# ==================== 对比：本地 vs 云端 ====================

def tag_of(title):
    m = TAG_RE.search(title or "")
    return m.group(1) if m else None


def artifact_kind(a):
    return "quiz" if a.is_quiz else "flashcards" if a.is_flashcards else None


def artifact_title(week, kind):
    return f"Week {week} - {LABELS[kind]}"


def plan_sources(plan, cloud_sources):
    """决定保留、删除、上传哪些来源。"""
    local_tags = {f.tag for f in plan.files}
    for s in cloud_sources:
        tag = tag_of(s.title)
        failed = getattr(s.status, "name", "") == "ERROR"
        if tag in local_tags and tag not in plan.source_by_tag and not failed:
            plan.source_by_tag[tag] = s.id
        else:  # 本地没有 / 没有标签 / 重复 / 处理失败
            plan.drop_sources.append(s)

    queued = set()
    for f in plan.files:
        if f.tag not in plan.source_by_tag and f.tag not in queued:
            plan.upload.append(f)
            queued.add(f.tag)


def plan_artifacts(plan, cloud_artifacts):
    """判断每个 quiz/闪卡是不是最新：来源集合必须和某一周本地文件完全一致。"""
    tag_by_id = {sid: tag for tag, sid in plan.source_by_tag.items()}
    kept = {}  # (周, 种类) -> 生成物
    week_tags = set().union(*plan.want.values()) if plan.want else set()

    for a in cloud_artifacts:
        kind = artifact_kind(a)
        if kind is None:
            continue  # 音频、思维导图等不碰
        if not a.source_ids:
            if a.is_completed:
                sys.exit("❌ 读不到 quiz/闪卡的来源记录（notebooklm-py 版本可能太旧），"
                         "为避免误删已停止。请先升级：pip install -U notebooklm-py")
            continue  # 还在生成中的，先不管

        if any(tag_by_id.get(sid) in plan.exam_tags for sid in a.source_ids):
            continue  # 用到了 EXAM 的来源 -> 是你自己做的，不碰

        tags = {tag_by_id.get(sid) for sid in a.source_ids}
        known = tags - {None}
        all_known = None not in tags  # 有来源已经被删或不认识 -> 旧版本
        ours = OUR_TITLE_RE.match(a.title or "")
        weeks = [w for w, want in plan.want.items() if all_known and want == tags]
        if ours:  # 名字里的周优先（几周内容完全一样时用来区分）
            weeks.sort(key=lambda w: w != int(ours.group(1)))

        slot = next((w for w in weeks if (w, kind) not in kept), None)
        if a.is_failed or slot is None:
            # 失败的 / 已过期的 / 多余的：确定是自己生成的才删
            # （名字对得上，或只用了周文件、其中有的已失效）；你手动做的不动
            stale_week_artifact = not all_known and bool(known) and known <= week_tags
            if (a.is_failed and weeks) or ours or stale_week_artifact:
                plan.drop_artifacts.append(a)
            continue
        kept[(slot, kind)] = a
        plan.titles[a.id] = artifact_title(slot, kind)

    for week in sorted(plan.want):
        todo = [k for k in KINDS if (week, k) not in kept]
        if todo:
            plan.missing[week] = todo


async def build_plan(client, course, files, notebooks):
    plan = CoursePlan(course, files)
    for f in files:
        if not f.is_exam:
            plan.want.setdefault(f.week, set()).add(f.tag)
    plan.want = {w: frozenset(tags) for w, tags in plan.want.items()}
    week_tags = set().union(*plan.want.values()) if plan.want else set()
    plan.exam_tags = frozenset(f.tag for f in files if f.is_exam and f.tag not in week_tags)

    matches = notebooks.get(plan.code, [])
    if len(matches) > 1:
        print(f"⚠️  有 {len(matches)} 个笔记本都叫 {plan.code}，只处理第一个。")
    if matches:
        plan.nb_id = matches[0].id
        plan_sources(plan, await client.sources.list(plan.nb_id))
        plan_artifacts(plan, await client.artifacts.list(plan.nb_id))
    else:
        plan_sources(plan, [])
        plan_artifacts(plan, [])
    return plan


def print_plans(plans):
    for plan in plans:
        print(f"== {plan.code} ==")
        if not plan.has_work:
            print("  已是最新")
            continue
        if plan.nb_id is None:
            print("  新建笔记本")
        if plan.upload:
            print(f"  上传 {len(plan.upload)} 个：" + "、".join(
                f.path.name + ("（EXAM）" if f.is_exam else "") for f in plan.upload))
        if plan.drop_sources:
            print(f"  删除云端来源 {len(plan.drop_sources)} 个：" +
                  "、".join(s.title or "(无标题)" for s in plan.drop_sources))
        if plan.drop_artifacts:
            print(f"  删除旧 quiz/闪卡 {len(plan.drop_artifacts)} 个：" +
                  "、".join(a.title or "(无标题)" for a in plan.drop_artifacts))
        if plan.missing:
            print("  需要生成：" + "；".join(
                f"Week {w}（{' + '.join(LABELS[k] for k in ks)}）" for w, ks in sorted(plan.missing.items())))


# ==================== 执行：同步来源 ====================

async def upload_file(client, plan, f):
    print(f"⬆️  上传 {f.path.name}")
    try:
        src = await client.sources.add_file(plan.nb_id, f.path, wait=True, title=f.title)
    except Exception as e:
        print(f"   ❌ 上传失败：{type(e).__name__}: {e}")
        return
    if tag_of(getattr(src, "title", None)) != f.tag:  # 标题没带上哈希，补改一次
        try:
            await client.sources.rename(plan.nb_id, src.id, f.title)
        except Exception as e:
            print(f"   ⚠️  没能把哈希写进标题（{type(e).__name__}），下次运行会被当成多余来源重传")
    plan.source_by_tag[f.tag] = src.id
    await asyncio.sleep(UPLOAD_GAP)


async def apply_sync(client, plan):
    """让云端来源和本地一致，并清掉旧的 quiz/闪卡。"""
    if plan.nb_id is None:
        nb = await client.notebooks.create(plan.code)
        plan.nb_id = nb.id
        print(f"📒 新建笔记本：{plan.code}")

    for a in plan.drop_artifacts:
        try:
            await client.artifacts.delete(plan.nb_id, a.id)
            print(f"🗑️  已删除旧的 {a.title}")
        except Exception as e:
            print(f"⚠️  删除 {a.title} 失败（可手动删）：{type(e).__name__}")

    if plan.drop_sources:
        try:
            await client.sources.delete_many(plan.nb_id, [s.id for s in plan.drop_sources])
            print(f"🗑️  已删除 {len(plan.drop_sources)} 个多余来源（{plan.code}）")
        except Exception as e:
            print(f"⚠️  删除来源失败（{plan.code}）：{type(e).__name__}: {e}")

    for f in plan.upload:
        await upload_file(client, plan, f)


# ==================== 执行：生成 quiz / 闪卡 ====================

async def request_generation(client, nb_id, kind, prompt, source_ids):
    """发起生成，返回任务 id。被限速时等一下再试一次，仍被限速就抛出 RateLimitError。"""
    gen = client.artifacts.generate_quiz if kind == "quiz" else client.artifacts.generate_flashcards
    try:
        status = await gen(nb_id, source_ids=source_ids, instructions=prompt)
    except RateLimitError:
        print(f"   ⚠️  {LABELS[kind]} 被限速，{RATE_WAIT} 秒后重试一次…")
        await asyncio.sleep(RATE_WAIT)
        status = await gen(nb_id, source_ids=source_ids, instructions=prompt)
    return status.task_id


async def generate_one(client, plan, week, kind, prompt, source_ids):
    label = LABELS[kind]
    title = artifact_title(week, kind)

    try:
        task_id = await request_generation(client, plan.nb_id, kind, prompt, source_ids)
    except RateLimitError:
        return Outcome.LIMIT
    except Exception as e:
        print(f"   ❌ {label} 失败：{type(e).__name__}: {e}")
        return Outcome.FAIL

    try:
        status = await client.artifacts.wait_for_completion(plan.nb_id, task_id, timeout=GEN_TIMEOUT)
        if getattr(status, "error", None):
            raise RuntimeError(f"生成失败：{status.error}")
    except Exception as e:
        print(f"   ❌ {label} 失败：{type(e).__name__}: {e}")
        return Outcome.FAIL

    plan.titles[task_id] = title
    try:
        await client.artifacts.rename(plan.nb_id, task_id, title)
    except Exception as e:
        print(f"   （重命名失败，结束时会再试：{type(e).__name__}）")
    print(f"   ✅ {title}")
    return Outcome.OK


async def generate_week(client, plan, week, prompts):
    """同时生成这一周缺的 quiz 和闪卡。"""
    print(f"== {plan.code} · Week {week} ==")
    tags = sorted(plan.want[week])
    if any(t not in plan.source_by_tag for t in tags):
        print("   ⏭️  这一周有文件没上传成功，先跳过（重新运行会补上）")
        return [Outcome.FAIL]
    source_ids = [plan.source_by_tag[t] for t in tags]
    kinds = plan.missing[week]
    print(f"⏳ 生成 {' 和 '.join(LABELS[k] for k in kinds)}…")
    return await asyncio.gather(*(
        generate_one(client, plan, week, k, prompts[k], source_ids) for k in kinds
    ))


async def fix_names(client, plans):
    """检查 quiz/闪卡的名字，被 NotebookLM 改掉的改回 'Week N - Quiz/Flashcards'。"""
    fixed = 0
    for plan in plans:
        if not plan.nb_id or not plan.titles:
            continue
        try:
            artifacts = await client.artifacts.list(plan.nb_id)
        except Exception as e:
            print(f"（读取 {plan.code} 的内容失败：{type(e).__name__}）")
            continue
        for a in artifacts:
            want = plan.titles.get(a.id)
            if want and a.title != want:
                try:
                    await client.artifacts.rename(plan.nb_id, a.id, want)
                    fixed += 1
                except Exception as e:
                    print(f"（改名失败 {want}：{type(e).__name__}）")
    if fixed:
        print(f"🔤 已把 {fixed} 个名字改回 Week N 格式。")


# ==================== 主流程 ====================

def parse_args():
    ap = argparse.ArgumentParser(description="让 NotebookLM 和本地 Week 文件夹保持一致并生成 quiz/闪卡")
    ap.add_argument("--dry-run", action="store_true", help="只显示计划，不做任何改动")
    ap.add_argument("--yes", action="store_true", help="有删除操作时不再询问确认")
    return ap.parse_args()


async def main():
    args = parse_args()

    local, unsupported = scan_local()
    if unsupported:
        names = "、".join(p.name for p in unsupported[:5]) + ("…" if len(unsupported) > 5 else "")
        print(f"⚠️  有 {len(unsupported)} 个文件类型不支持上传，已跳过：{names}")
    if not local:
        sys.exit("在 UM_Courses 里没找到 Week / EXAM 文件夹里的课件，请先运行 spectrum_download.py。")
    for course, files in local.items():
        check_collisions(course, files)
    prompts = {k: read_prompt(k) for k in KINDS}

    async with NotebookLMClient.from_storage() as client:
        notebooks = {}
        for nb in await client.notebooks.list():
            notebooks.setdefault(nb.title, []).append(nb)

        plans = [await build_plan(client, course, files, notebooks)
                 for course, files in sorted(local.items())]
        print_plans(plans)

        if not any(p.has_work for p in plans):
            await fix_names(client, plans)
            print("\n云端已经和本地一致，没有需要处理的内容。")
            return
        if args.dry_run:
            print("\n（--dry-run：只显示计划，没有做任何改动）")
            return
        if any(p.destructive for p in plans) and not args.yes:
            if input("\n会删除上面列出的云端内容，继续？[y/N] ").strip().lower() != "y":
                sys.exit("已取消。")
        print()

        # 第一步：所有课先同步来源
        for plan in plans:
            if plan.has_work:
                await apply_sync(client, plan)

        # 第二步：先做所有课的小周，再做大周
        jobs = sorted(((w, p.code, p) for p in plans for w in p.missing), key=lambda j: j[:2])
        made, failed, limited = 0, [], False
        for week, code, plan in jobs:
            results = await generate_week(client, plan, week, prompts)
            made += results.count(Outcome.OK)
            if any(r is not Outcome.OK for r in results):
                failed.append(f"{code} Week {week}")
            if Outcome.LIMIT in results:
                limited = True
                print("\n🛑 一直被限速（很可能是额度用完了），已终止。等额度恢复后重新运行，会从这里接着做。")
                break

        if made:
            await asyncio.sleep(NAME_CHECK_DELAY)  # 名字可能被 NotebookLM 事后改掉
        await fix_names(client, plans)

    print(f"\n本次生成了 {made} 份内容。")
    if failed:
        print("没生成完整的周：" + "、".join(failed))
    if failed or limited:
        print("重新运行脚本会自动接着做（已上传的文件不会重复上传）。")


if __name__ == "__main__":
    asyncio.run(main())
