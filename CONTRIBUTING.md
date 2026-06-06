# Contributing

Thank you for improving YOLO Annotator Desktop.

## Ground Rules

- Keep the application local-first and usable without an account or server.
- Preserve standard YOLO text compatibility.
- Never silently discard or remap labels without creating a backup.
- Keep interaction latency low on large images.
- Add tests for project, class-remapping, QC, and export behavior.

## Before Opening a Pull Request

```powershell
py -m unittest discover -s tests -v
```

Describe the user-facing behavior, data-safety implications, and manual checks
performed.
