"""Nox sessions."""
import json
import os
import pathlib
import shutil
import tempfile
import textwrap

import nox
from nox.sessions import Session

nox.needs_version = ">= 2021.6.6"
LIBRARY_REPOSITORY = "seaborn"
LIBRARY_NAME = "seaborn"
UPSTREAM_REPOSITORY_OWNER = "Kapeli"
DOCSET_REPOSITORY = "Dash-User-Contributions"
DASH_DOCSET_PATH = pathlib.Path(DOCSET_REPOSITORY, "docsets", LIBRARY_NAME)
GITHUB_USER = "paw-lu"
GITHUB_REPO = "seaborn-dash2doc"


@nox.session
def clone(session: Session) -> None:
    """Clone the repository and checkout latest release."""
    repository_owner = "mwaskom"
    repository_address = f"{repository_owner}/{LIBRARY_REPOSITORY}"
    session.run("gh", "repo", "clone", repository_address, external=True)

    with session.chdir(LIBRARY_REPOSITORY):
        latest_release_tag_name = session.run(
            "gh",
            "api",
            "--header=Accept: application/vnd.github+json",
            "/repos/mwaskom/seaborn/releases/latest",
            "--jq=.tag_name",
            external=True,
            silent=True,
        ).rstrip()
        session.run(
            "git",
            "checkout",
            f"tags/{latest_release_tag_name}",
            "-b",
            latest_release_tag_name,
            external=True,
        )


@nox.session
def docs(session: Session) -> None:
    """Build seaborn's docs."""
    with session.chdir(LIBRARY_REPOSITORY):
        session.install(".[stats]")

    with session.chdir(f"{LIBRARY_REPOSITORY}/doc"):
        kernel_name = f"{LIBRARY_NAME}_docs"
        session.install("--requirement", "requirements.txt")
        session.run(
            "python", "-m", "ipykernel", "install", "--user", f"--name={kernel_name}"
        )
        session.run(
            "make", "notebooks", "html", external=True, env={"NB_KERNEL": kernel_name}
        )


@nox.session
def icon(session: Session) -> None:
    """Create dash icon."""
    for size, file_name in (("16x16", "icon.png"), ("32x32", "icon@2x.png")):
        session.run(
            "magick",
            "seaborn/doc/_build/html/_static/logo-mark-lightbg.png",
            "-resize",
            size,
            file_name,
            external=True,
        )


@nox.session
def dash(session: Session) -> None:
    """Create dash docset."""
    session.install("doc2dash")
    session.run(
        "doc2dash",
        "--index-page=index.html",
        "--icon=icon.png",
        "--online-redirect-url=https://seaborn.pydata.org/",
        f"{LIBRARY_REPOSITORY}/doc/_build/html",
        *session.posargs,
    )
    # As of 3.0.0, doc2dash does not support 2x icons
    # See https://github.com/hynek/doc2dash/issues/130
    shutil.copy("icon@2x.png", f"{LIBRARY_NAME}.docset/")


def _get_library_version(session: Session) -> str:
    """Get the version for the library."""
    with tempfile.NamedTemporaryFile() as dependency_report_file:
        session.run(
            "python",
            "-m",
            "pip",
            "install",
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
    library_version = library_install_report["metadata"]["version"]

    return library_version


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
    ).rstrip()

    return default_branch


def _make_branch_name(session: Session) -> str:
    """Create name for branch on Dash-User-Contributions repo."""
    library_version = _get_library_version(session)
    branch_name = f"{LIBRARY_NAME}-{library_version}"

    return branch_name


@nox.session
def fork(session: Session) -> None:
    """Fork Dash user contributed docsets and create new branch."""
    session.run(
        "gh",
        "repo",
        "fork",
        "--clone",
        f"{UPSTREAM_REPOSITORY_OWNER}/{DOCSET_REPOSITORY}",
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


@nox.session(name="create-directory")
def create_directory(session: Session) -> None:
    """If directory for docset does not exist, create it."""
    with session.chdir(DOCSET_REPOSITORY):
        docset_path = pathlib.Path("docsets", LIBRARY_NAME)
        docset_path.mkdir(exist_ok=True)


@nox.session(name="remove-old")
def remove_old(session: Session) -> None:
    """Remove old docsets."""
    shutil.rmtree(DASH_DOCSET_PATH / "versions")

    for old_zipped_docset in DASH_DOCSET_PATH.glob("*.tgz*"):
        old_zipped_docset.unlink()


@nox.session(name="copy-contents")
def copy_contents(session: Session) -> None:
    """Copy build docset contents into Dash User Contributions repo."""
    build_path = pathlib.Path(f"{LIBRARY_NAME}.docset")

    for icon_path in build_path.glob("icon*.png"):
        shutil.copy(icon_path, DASH_DOCSET_PATH)

    zipped_docset_path = os.fsdecode(
        (DASH_DOCSET_PATH / LIBRARY_NAME).with_suffix(".tgz")
    )
    session.run(
        "tar",
        "--exclude=.DS_Store",
        "-cvzf",
        zipped_docset_path,
        f"{LIBRARY_NAME}.docset",
        external=True,
    )


@nox.session(name="fill-forms")
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
            "url": docset_author_url,
        },
        "aliases": ["python", "graph", "matplotlib", "visualization", "data"],
    }
    dash_path = pathlib.Path(DOCSET_REPOSITORY, "docsets", LIBRARY_NAME)
    docset_config_path = (dash_path / "docset").with_suffix(".json")
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

        $ nox --sessions clone docs icon dash
        ```
    """
    )
    (dash_path / "README").with_suffix(".md").write_text(readme)


@nox.session
def commit(session: Session) -> None:
    """Commit changes to Dash User Contributed Docs."""
    library_version = _get_library_version(session)

    with session.chdir(DASH_DOCSET_PATH):
        session.run("git", "add", ".", external=True)
        session.run(
            "git",
            "commit",
            f"--message=Add docset for {LIBRARY_NAME} {library_version}.",
            external=True,
        )


@nox.session
def push(session: Session) -> None:
    """Push the branch to the user's remote."""
    branch_name = _make_branch_name(session)
    session.run("git", "push", "--set-upstream", "origin", branch_name)
