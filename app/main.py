import sys


def main() -> None:
    print(f"ParcelLens OK — Python {sys.version.split()[0]}")
    print(f"Interpreter: {sys.executable}")  # proves we're running inside .venv


if __name__ == "__main__":
    main()
