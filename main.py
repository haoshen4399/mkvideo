import faulthandler
import os

from app.cli import main


def _configure_process_safety() -> None:
    faulthandler.enable(all_threads=True)
    if os.name != "nt":
        return
    try:
        import ctypes

        sem_failcriticalerrors = 0x0001
        sem_nogpfault_errorbox = 0x0002
        sem_noopenfile_errorbox = 0x8000
        ctypes.windll.kernel32.SetErrorMode(
            sem_failcriticalerrors | sem_nogpfault_errorbox | sem_noopenfile_errorbox
        )
    except Exception:
        pass


if __name__ == "__main__":
    _configure_process_safety()
    main()
