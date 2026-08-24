using ExplicitImports

root = realpath(get(ARGS, 1, "."))
pushfirst!(LOAD_PATH, root)
exit(ExplicitImports.main(["--check", "--checklist", "all", root]))
