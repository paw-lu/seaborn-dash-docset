"""Nox sessions."""
import shutil

import nox
from nox.sessions import Session

nox.needs_version = ">= 2021.6.6"
REPOSITORY_NAME = "seaborn"


@nox.session
def clone(session: Session) -> None:
    """Clone the repository."""
    github_account = "mwaskom"
    repository_address = f"{github_account}/{REPOSITORY_NAME}"
    session.run("gh", "repo" "clone", repository_address)

    with session.chdir(REPOSITORY_NAME):
        releases_output = session.run(
            "gh", "release", "list", external=True, silent=True
        )

        for releases in releases_output.splitlines():
            release_name, release, release_tag, *_ = releases.split()

            if release == "Latest":
                break

        else:
            raise ValueError("Found no 'Latest' tagged release.")

        session.run("git", "checkout", f"tags/{release_tag}", "-b", release_name)


@nox.session
def docs(session: Session) -> None:
    """Build seaborn's docs."""
    with session.chdir(REPOSITORY_NAME):
        session.install(".[stats]")

    with session.chdir(f"{REPOSITORY_NAME}/doc"):
        kernel_name = "seaborn_docs"
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
    shutil.copy("icon@2x.png", f"{REPOSITORY_NAME}.docset/")
