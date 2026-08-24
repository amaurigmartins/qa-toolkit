using Aqua
using TOML

root = realpath(get(ARGS, 1, "."))
project = TOML.parsefile(joinpath(root, "Project.toml"))
name = get(project, "name", nothing)
name isa String || error("Project.toml requires a package name for Aqua")
pushfirst!(LOAD_PATH, root)
target_module = Base.require(Main, Symbol(name))
Aqua.test_all(target_module)
