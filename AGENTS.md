## 1. Data File Handling Rules (MANDATORY — highest priority)

These rules apply to every file in this project.

### 1.1 Ask before reading

- Never open, read, or process a file without asking me first and receiving explicit approval.
- This applies to every method of access: file-reading tools, `cat`, `head`, `tail`, `less`, `grep`, `sed`, `awk`, pandas/Python scripts, or any other command that outputs file contents.
- Approval is per file. Permission to read one file does not extend to other files or to later requests.
- When asking, name the file and briefly explain why you need it.


<!-- ### 1.2 Row limit: 100 rows maximum

- Even with approval, read no more than 100 rows per file. Header row plus 99 data rows, or header plus 100 data rows, is fine, as long as it never goes beyond 100 data rows.
- Use bounded commands, for example `head -n 101 file.csv` or `pd.read_csv(path, nrows=100)`.
- Never load a whole CSV into memory or print its full contents.
- If a task needs more than 100 rows, stop and ask me. Do not work around the limit by reading in chunks or repeated passes. -->


### 1.3 No workarounds

- Do not infer file contents from other sources (logs, cached outputs, other files) to avoid asking.
- Do not write scripts that read the full file, even if you only intend to show 10 rows of output.
- If you're unsure whether a file counts as CSV data, treat it as if it does and ask.

### 1.4 Reading PDFs

- If you read PDF files doublecheck with the user its contents.
- Before you give information about something you found in the PDF file, always tell the user what you know.
- If you are unsure about some specifications ask for the formula from the user.