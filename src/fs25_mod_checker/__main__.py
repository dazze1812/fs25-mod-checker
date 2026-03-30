try:
    from . import main
except ImportError:
    # PyInstaller may execute this file as a top-level script.
    from fs25_mod_checker import main

if __name__ == "__main__":
    main()