# Spectrum-Moodle-notebook-workflow
Automatically download moodle/spectrum files and upload to LM notebook and generate quiz and flashcards.

## Qick start:
All files are needed to put in the same folder, any name is fine (ex. folder X)

1.Go to your spectrum profile, click Preferences, click Security keys, click reset for Moodle mobile web service, then you can get your token. Don't share.

2.Put your token in text file. Then put this file into X.

3.moodle_deadlines: Get all the assignments and quiz inside or outside due. And check details.

4.spectrum_announcements: Get 48 hours and inside 2 weeks' announcements. And check details.

5.spectrum_download: download the all course files from spectrum

6.notebooklm_pipeline: upload files to notebooklm. And generate quizs and flashcards for each week. (need to put folder "prompts" inside the X first)

有想跳过的课，往 EXCLUDE_COURSES 里加课程代码就可以，不分大小写。
