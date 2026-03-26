## Schedule refresh on Windows (Task Scheduler)

This project scrapes LinkedIn jobs via `jobsparser`. To reduce blocks/captchas, keep refresh frequency modest (for example, daily or a few times per day).

### Create a task

1. Open **Task Scheduler**
2. **Create Basic Task…**
3. Trigger: Daily (or repeat every 6 hours)
4. Action: Start a program
   - Program/script: `powershell.exe`
    - Add arguments:
     - `-NoProfile -ExecutionPolicy Bypass -Command "cd D:\Coding_Project\jobboard_econ; .\.venv312\Scripts\Activate.ps1; python .\scripts\refresh.py --scrape"`
   - Start in:
     - `D:\Coding_Project\jobboard_econ`

### Notes

- If you don’t want `ExecutionPolicy Bypass`, run the equivalent with your own policy settings.
- You can also run refresh manually:
  - `python .\scripts\refresh.py`

