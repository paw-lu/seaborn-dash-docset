# Seaborn dash docset

Generates a [documentation set](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/Documentation_Sets/010-Overview_of_Documentation_Sets/docset_overview.html#//apple_ref/doc/uid/TP40005266-CH13-SW6)
for [Seaborn](https://github.com/mwaskom/seaborn)
for use in [Dash](https://kapeli.com/dash) compatible API browsers using
[doc2dash](https://doc2dash.readthedocs.io/en/stable/)
and automatically contributes it to [Kapeli/Dash-User-Contributions](https://github.com/Kapeli/Dash-User-Contributions)
so that it may be available for others.

## How this project works

1. When a new version of [Seaborn](https://github.com/mwaskom/seaborn) releases,
   A pull request is created by [Dependabot](https://github.com/dependabot)
   updating `doc-requirements.txt`.
2. An update of `doc-requirements.txt` will trigger the docs to build
   on the newest tagged release of [Seaborn](https://github.com/mwaskom/seaborn)
   (`nox --tags build`).
3. A pull request will be generated
   contributing the docset to [Kapeli/Dash-User-Contributions](https://github.com/Kapeli/Dash-User-Contributions)
   where it will be available to others after it is merged.
