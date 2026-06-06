import argparse

from .app import run


def main():
    parser = argparse.ArgumentParser(description="YOLO Annotator Desktop")
    parser.add_argument("--project", default="", help="Optional .yad.json project file to open")
    args = parser.parse_args()
    run(args.project)


if __name__ == "__main__":
    main()
