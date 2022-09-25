"""Nox sessions."""
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
