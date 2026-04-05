# Development

The extension is split into a bunch of different files. Each time you make a change, you will have to reload scripts.
To do so, click `(Blender Icon) > System > Reload Scripts`. I personally mapped this to `F8` for convenience.

# Code style.

Use clean and consistent code styling.
Type hints should be used where appropriate.

You must format your code using [Black](https://github.com/psf/black). You can do this by running:

`pip install -r requirements.dev.txt`

`black .`

## Release

Before packaging or running from source, execute these commands to fetch dependencies:

`pip wheel --no-deps -r requirements.txt -w ./wheels`

This is to comply with the [Python Wheels rules](https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html) for the [Blender Extensions](https://extensions.blender.org/) platform.

# Github Actions

You can use [act](https://github.com/nektos/act) to test the GitHub action workflow.

`act -P windows-latest=-self-hosted -j build`