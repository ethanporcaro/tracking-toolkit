# Development

The extension is split into a bunch of different files. Each time you make a change, you will have to reload scripts.
To do so, click `(Blender Icon) > System > Reload Scripts`. I personally mapped this to `F8` for convenience.

## Release

Before packaging or running from source, execute these commands to fetch dependencies:

`pip wheel openvr -w ./wheels`

This is to comply with the [Python Wheels rules](https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html) for the [Blender Extensions](https://extensions.blender.org/) platform.