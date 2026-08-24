using JuliaFormatter

root = realpath(get(ARGS, 1, "."))
expected_version = get(ARGS, 2, "")
actual_version = string(pkgversion(JuliaFormatter))
actual_version == expected_version || error(
    "JuliaFormatter version mismatch: expected $(expected_version), loaded $(actual_version)",
)
println("qa-toolkit-julia-formatter=$(actual_version)")
excluded = Set([".git", ".qat", ".julia", "deps", "toolkit"])
failures = String[]

for (directory, directories, names) in walkdir(root)
    filter!(name -> !(name in excluded), directories)
    for name in names
        endswith(name, ".jl") || continue
        path = joinpath(directory, name)
        JuliaFormatter.format(path; overwrite = false) || push!(failures, relpath(path, root))
    end
end

if !isempty(failures)
    for path in sort(failures)
        println(stderr, path, ": JuliaFormatter would change this file")
    end
    exit(1)
end
