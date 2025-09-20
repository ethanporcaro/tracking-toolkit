# Development

The extension is split into a bunch of different files. Each time you make a change, you will have to reload scripts.
To do so, click `(Blender Icon) > System > Reload Scripts`. I personally mapped this to `F8` for convenience.

## Release

Before running from source, execute these commands to fetch dependencies:

`pip download --only-binary :all: --dest ./wheels --no-deps -r requirements.txt`

This is to comply with the [Python Wheels rules](https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html) for the [Blender Extensions](https://extensions.blender.org/) platform.