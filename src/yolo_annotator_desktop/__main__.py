import argparse

from .app import run


def main():
    parser = argparse.ArgumentParser(description="YOLO Annotator Desktop")
    parser.add_argument("--project", default="", help="Optional .yad.json project file to open")
    parser.add_argument("--hub", action="store_true", help="Open the project hub instead of directly opening the annotator")
    args = parser.parse_args()
    run(args.project, hub=args.hub)


if __name__ == "__main__":
    main()
