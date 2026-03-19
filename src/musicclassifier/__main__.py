"""允许 python -m musicclassifier 直接启动 UI"""

import sys
import subprocess


def main():
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run",
         __file__.replace("__main__.py", "ui/app.py"),
         "--server.headless", "true"],
    )


if __name__ == "__main__":
    main()
