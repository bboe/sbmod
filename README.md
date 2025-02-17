# sbmod

## Prerequisites

In order to run this code you will need a user account with the necessary credentials provided in a
`sbmod` section of your `praw.ini` file. The user-account will need the following moderator
permissions on the desired subreddit:

- Manage Mod Mail
- Manage Users


## Running

1. Ensure UV is installed [[instructions](https://docs.astral.sh/uv/getting-started/installation/)]

2. Download or clone source code and from the source directory run:

```sh
uv run sbmod
```

Use `--help` to see what commands are available.


## Developing

Verify existing tests pass by running:

```sh
uv run tox
```

Modify code as desired and continue to fix test issues as needed.
