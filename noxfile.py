"""Nox sessions."""
import functools
import json
import os
import pathlib
import shutil
import tempfile
import textwrap
from pathlib import Path
from urllib import parse

import nox
from nox.sessions import Session

nox.needs_version = ">= 2021.6.6"
nox.options.stop_on_first_error = True

CONSTRAINTS_ARG = "--constraint=.github/workflows/constraints.txt"
LIBRARY_REPOSITORY = "seaborn.github.io"
LIBRARY_NAME = "seaborn"
UPSTREAM_REPOSITORY_OWNER = "Kapeli"
DOCSET_REPOSITORY = "Dash-User-Contributions"
GITHUB_USER = "paw-lu"
GITHUB_REPO = "seaborn-dash-docset"
# This is necessary to make nox run on specified python
# Follow https://github.com/wntrblm/nox/issues/623 to see if it
# eventually changes
PYTHON = "3.10"


@nox.session(python=False, tags=["build"])
def clone(session: Session) -> None:
    """Clone the repository and checkout latest release."""
    repository_owner = "seaborn"
    repository_address = f"{repository_owner}/{LIBRARY_REPOSITORY}"
    session.run("gh", "repo", "clone", repository_address, external=True)

    with session.chdir(LIBRARY_REPOSITORY):
        tags_api_output = session.run(
            "gh",
            "api",
            "--header=Accept: application/vnd.github+json",
            f"/repos/{repository_address}/tags",
            "--jq=.[].name",
            external=True,
            silent=True,
        )

        if isinstance(tags_api_output, str):
            tag_names = tags_api_output.split()
            numeric_tag_names = [
                tag_name
                for tag_name in tag_names
                if tag_name.replace("v", "").replace(".", "").isnumeric()
            ]
            latest_tag_name = max(
                numeric_tag_names,
                key=lambda tag_name: tuple(
                    int(version_section)
                    for version_section in tag_name.replace("v", "").split(".")
                ),
            )
            session.run(
                "git",
                "checkout",
                f"tags/{latest_tag_name}",
                "-b",
                latest_tag_name,
                external=True,
            )

        else:
            raise ValueError("Did not find a tag name for the latest release")


@nox.session(python=False, tags=["build"])
def icon(session: Session) -> None:
    """Create dash icon."""
    for size, file_name in (("16x16", "icon.png"), ("32x32", "icon@2x.png")):
        # Using convert instead of magick since only the former is
        # available by default right now in ubuntu-latest
        session.run(
            "convert",
            f"{LIBRARY_REPOSITORY}/_static/logo-mark-lightbg.png",
            "-resize",
            size,
            "-background",
            "none",
            "-gravity",
            "center",
            "-extent",
            size,
            file_name,
            external=True,
        )


def _get_docset_path() -> Path:
    """Get path to created docset."""
    docset_path = next(pathlib.Path(__file__).parent.glob("*.docset"))

    return docset_path


@nox.session(python=PYTHON, tags=["build"])
def dash(session: Session) -> None:
    """Create dash docset."""
    session.install("doc2dash", CONSTRAINTS_ARG)
    session.run(
        "doc2dash",
        "--index-page=index.html",
        "--icon=icon.png",
        "--online-redirect-url=https://seaborn.pydata.org/",
        f"{LIBRARY_REPOSITORY}",
        *session.posargs,
    )
    # As of 3.0.0, doc2dash does not support 2x icons
    # See https://github.com/hynek/doc2dash/issues/130
    docset_path = _get_docset_path()
    shutil.copy("icon@2x.png", os.fsdecode(docset_path))


@functools.lru_cache
def _get_library_version(session: Session) -> str:
    """Get the version for the library."""
    with tempfile.NamedTemporaryFile() as dependency_report_file:
        session.install(
            "--dry-run",
            "--no-deps",
            "--ignore-installed",
            "--report",
            dependency_report_file.name,
            "--requirement",
            "doc-requirements.txt",
        )
        dependency_report = json.load(dependency_report_file.file)

    install_report = dependency_report["install"]

    if 1 < len(install_report):
        raise ValueError(
            "Multiple dependencies detected in requirements file. Expected one."
        )

    library_install_report, *_ = install_report
    library_version: str = library_install_report["metadata"]["version"]

    return library_version


@functools.lru_cache
def _get_trunk_branch_name(
    session: Session, repository_owner: str, repository_name: str
) -> str:
    """Get name of trunk branch."""
    default_branch = session.run(
        "gh",
        "api",
        "--header=Accept: application/vnd.github+json",
        f"/repos/{repository_owner}/{repository_name}",
        "--jq=.default_branch",
        external=True,
        silent=True,
    )

    if isinstance(default_branch, str):
        return default_branch.rstrip()

    else:
        raise ValueError("No default branch detected.")


@functools.lru_cache
def _make_branch_name(session: Session) -> str:
    """Create name for branch on Dash-User-Contributions repo."""
    library_version = _get_library_version(session)
    branch_name = f"{LIBRARY_NAME}-{library_version}"

    return branch_name


def _add_github_token(repo_url: str, github_token: str) -> str:
    """Add a GitHub token to a repository URL.

    Needed to authenticate pushes to other repositories on GitHub
    Actions.
    """
    split_url = parse.urlsplit(repo_url)
    token_netloc = f"{github_token}@{split_url.netloc}"
    token_url = split_url._replace(netloc=token_netloc).geturl()

    return token_url


@nox.session(python=PYTHON, tags=["contribute"])
def fork(session: Session) -> None:
    """Fork Dash user contributed docsets and create new branch."""
    session.run(
        "gh",
        "repo",
        "fork",
        "--clone",
        f"{UPSTREAM_REPOSITORY_OWNER}/{DOCSET_REPOSITORY}",
        "--remote",
        external=True,
    )
    branch_name = _make_branch_name(session)

    with session.chdir(DOCSET_REPOSITORY):
        session.run(
            "git",
            "switch",
            "--create",
            branch_name,
            external=True,
        )
        session.run("git", "fetch", "upstream", external=True)
        trunk_branch_name = _get_trunk_branch_name(
            session,
            repository_owner=UPSTREAM_REPOSITORY_OWNER,
            repository_name=DOCSET_REPOSITORY,
        )
        session.run(
            "git", "reset", "--hard", f"upstream/{trunk_branch_name}", external=True
        )

        if (
            os.environ.get("GITHUB_ACTION") == "contribute-docs"
            and (github_token := os.environ.get("GITHUB_TOKEN")) is not None
        ):
            origin_url = session.run(
                "git", "remote", "get-url", "origin", silent=True, external=True
            )

            if isinstance(origin_url, str):
                token_url = _add_github_token(origin_url, github_token=github_token)
                session.run("git", "remote", "remove", "origin", external=True)
                session.run("git", "remote", "add", "origin", token_url, external=True)

            else:
                raise ValueError("No url for remote 'origin' detected.")


@functools.lru_cache
def _get_dash_docset_path() -> Path:
    """Get the name for the directory in the docset."""
    docset_directory = pathlib.Path(DOCSET_REPOSITORY, "docsets")

    for library_docset_path in docset_directory.iterdir():
        lowered_library_name = LIBRARY_NAME.lower()

        if (
            library_docset_path.is_dir()
            and lowered_library_name == library_docset_path.name.lower()
        ):
            return library_docset_path

    else:
        return docset_directory / LIBRARY_NAME


@nox.session(python=False, name="create-directory", tags=["contribute"])
def create_directory(session: Session) -> None:
    """If directory for docset does not exist, create it."""
    docset_path = _get_dash_docset_path()
    docset_path.mkdir(exist_ok=True)


@nox.session(python=False, name="remove-old", tags=["contribute"])
def remove_old(session: Session) -> None:
    """Remove old docsets."""
    dash_docset_path = _get_dash_docset_path()

    if (versions_path := dash_docset_path / "versions").exists():
        shutil.rmtree(versions_path)

    for old_zipped_docset in dash_docset_path.glob("*.tgz*"):
        old_zipped_docset.unlink()


@nox.session(python=False, name="copy-contents", tags=["contribute"])
def copy_contents(session: Session) -> None:
    """Copy build docset contents into Dash User Contributions repo."""
    docset_path = _get_docset_path()
    dash_docset_path = _get_dash_docset_path()

    for icon_path in docset_path.glob("icon*.png"):
        shutil.copy(icon_path, dash_docset_path)

    zipped_docset_path = os.fsdecode(
        (dash_docset_path / LIBRARY_NAME).with_suffix(".tgz")
    )
    session.run(
        "tar",
        "--exclude=.DS_Store",
        "-cvzf",
        zipped_docset_path,
        os.fsdecode(docset_path.name),
        external=True,
    )


@nox.session(python=PYTHON, name="fill-forms", tags=["contribute"])
def fill_forms(session: Session) -> None:
    """Fill forms for Dash User Contribution docs."""
    library_version = _get_library_version(session)
    docset_author = "Paulo S. Costa"
    docset_author_url = f"https://github.com/{GITHUB_USER}"
    docset_config = {
        "name": LIBRARY_NAME,
        "version": library_version,
        "archive": f"{LIBRARY_NAME}.tgz",
        "author": {
            "name": docset_author,
            "link": docset_author_url,
        },
        "aliases": ["python", "graph", "matplotlib", "visualization", "data"],
    }
    dash_docset_path = _get_dash_docset_path()
    docset_config_path = (dash_docset_path / "docset").with_suffix(".json")
    json.dump(docset_config, docset_config_path.open("w"), indent=2)
    repo_path = f"{GITHUB_USER}/{GITHUB_REPO}"
    readme = textwrap.dedent(
        f"""\
        # {LIBRARY_NAME}

        ## Who am I

        [{docset_author}]({docset_author_url})

        ## How to generate docset

        This docset is automatically generated via [{repo_path}](https://github.com/{repo_path}).

        ### Requirements

        - [git](https://git-scm.com/)
        - [GitHub CLI (gh)](https://cli.github.com/)
        - [GNU Make](https://www.gnu.org/software/make/)
        - [GNU Tar](https://www.gnu.org/software/tar/)
        - [ImageMagick](https://imagemagick.org/index.php)
        - [Nox](https://nox.thea.codes/en/stable/)
        - [Python 3](https://www.python.org/)

        ### Build directions

        To build the docs, run:

        ```console
        $ gh repo clone {repo_path}

        $ cd {GITHUB_REPO}

        $ nox --tags build
        ```
    """
    )
    (dash_docset_path / "README").with_suffix(".md").write_text(readme)


@nox.session(python=PYTHON, tags=["contribute"])
def commit(session: Session) -> None:
    """Commit changes to Dash User Contributed Docs."""
    library_version = _get_library_version(session)

    with session.chdir(DOCSET_REPOSITORY):
        session.run("git", "add", "--all", external=True)
        session.run(
            "git",
            "commit",
            f"--message=Add docset for {LIBRARY_NAME} {library_version}.",
            external=True,
        )


@nox.session(python=PYTHON, tags=["contribute"])
def push(session: Session) -> None:
    """Push the branch to the user's remote."""
    branch_name = _make_branch_name(session)

    with session.chdir(DOCSET_REPOSITORY):
        session.run(
            "git", "push", "--set-upstream", "origin", branch_name, external=True
        )


@nox.session(python=PYTHON, name="pull-request", tags=["contribute"])
def pull_request(session: Session) -> None:
    """Create a pull request for the Dash User Contributed Docs."""
    library_version = _get_library_version(session)
    dash_docset_path = _get_dash_docset_path()

    with session.chdir(dash_docset_path):
        trunk_branch_name = _get_trunk_branch_name(
            session,
            repository_owner=UPSTREAM_REPOSITORY_OWNER,
            repository_name=DOCSET_REPOSITORY,
        )
        pull_request_title = f"Add docset for {LIBRARY_NAME} {library_version}"
        repo_path = f"{GITHUB_USER}/{GITHUB_REPO}"
        pull_request_body = textwrap.dedent(
            f"""\
            {pull_request_title}.

            This pull request was generated by [{repo_path}](https://github.com/{repo_path}).
        """
        )
        branch_name = _make_branch_name(session)
        session.run(
            "gh",
            "pr",
            "create",
            f"--repo={UPSTREAM_REPOSITORY_OWNER}/{DOCSET_REPOSITORY}",
            f"--base={trunk_branch_name}",
            f"--title={pull_request_title}",
            f"--body={pull_request_body}",
            # Need to specify head for now
            # https://github.com/cli/cli/issues/6485#event-7645956185
            f"--head={GITHUB_USER}:{branch_name}",
            external=True,
        )


@nox.session(python=PYTHON, name="check-types", tags=["lint"])
def check_types(session: Session) -> None:
    """Check typing with mypy."""
    session.install("mypy", "nox", CONSTRAINTS_ARG)
    session.run("mypy", "noxfile.py")


@nox.session(python=PYTHON)
def version(session: Session) -> None:
    """Print the doc version."""
    library_version = _get_library_version(session)
    print(library_version)
