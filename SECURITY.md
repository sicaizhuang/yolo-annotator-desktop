# Security and Data Safety

YOLO Annotator Desktop runs locally and does not upload images or labels.

Before reporting a security issue, remove private datasets, paths, credentials,
and images from reproduction material.

Label, project, state, and report writes use same-directory atomic replacement.
The first edit to a label in each session creates a timestamped recovery copy.
Class-ID changes create a complete timestamped backup beside the source label
directory. Dataset export writes to a separate destination, never edits source
images, and refuses destinations inside source image or label directories.
