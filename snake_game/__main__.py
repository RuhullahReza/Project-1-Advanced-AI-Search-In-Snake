if __name__ == "__main__":
    import sys

    if "--text" in sys.argv:
        from .text_app import main
        main([arg for arg in sys.argv[1:] if arg != "--text"])
    else:
        from .app import main
        main()
