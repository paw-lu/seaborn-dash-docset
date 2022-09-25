"""Nox sessions."""
import json
import os
import pathlib
import shutil
import tempfile

import nox
from nox.sessions import Session

nox.needs_version = ">= 2021.6.6"
REPOSITORY_NAME = "seaborn"
LIBRARY_NAME = "seaborn"


@nox.session
def clone(session: Session) -> None:
    """Clone the repository and checkout latest release."""
    repository_owner = "mwaskom"
    repository_address = f"{repository_owner}/{REPOSITORY_NAME}"
    session.run("gh", "repo", "clone", repository_address, external=True)

    with session.chdir(REPOSITORY_NAME):
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
    with session.chdir(REPOSITORY_NAME):
        session.install(".[stats]")

    with session.chdir(f"{REPOSITORY_NAME}/doc"):
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
        f"{REPOSITORY_NAME}/doc/_build/html",
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


@nox.session
def fork(session: Session) -> None:
    """Fork Dash user contributed docsets and create new branch."""
    user_contributed_repo_owner = "Kapeli"
    user_contributed_repo = "Dash-User-Contributions"
    session.run(
        "gh",
        "repo",
        "fork",
        "--clone",
        f"{user_contributed_repo_owner}/{user_contributed_repo}",
        external=True,
    )
    library_version = _get_library_version(session)

    with session.chdir(user_contributed_repo):
        session.run(
            "git",
            "switch",
            "--create",
            f"{LIBRARY_NAME}-{library_version}",
            external=True,
        )
        session.run("git", "fetch", "upstream", external=True)
        trunk_branch_name = _get_trunk_branch_name(
            session,
            repository_owner=user_contributed_repo_owner,
            repository_name=user_contributed_repo,
        )
        session.run(
            "git", "reset", "--hard", f"upstream/{trunk_branch_name}", external=True
        )


@nox.session(name="create-directory")
def create_directory(session: Session) -> None:
    """If directory for docset does not exist, create it."""
    with session.chdir("Dash-User-Contributions"):
        docset_path = pathlib.Path("docsets", LIBRARY_NAME)
        docset_path.mkdir(exist_ok=True)


@nox.session(name="copy-contents")
def copy_contents(session: Session) -> None:
    """Copy build docset contents into Dash User Contributions repo."""
    build_path = pathlib.Path(f"{LIBRARY_NAME}.docset")
    dash_path = pathlib.Path("Dash-User-Contributions", "docsets", LIBRARY_NAME)

    for icon_path in build_path.glob("icon*.png"):
        shutil.copy(icon_path, dash_path)

    zipped_docset_path = os.fsdecode((dash_path / LIBRARY_NAME).with_suffix(".tgz"))
    session.run(
        "tar",
        "--exclude=.DS_Store",
        "-cvzf",
        zipped_docset_path,
        f"{LIBRARY_NAME}.docset",
        external=True,
    )
