package_name = Symbol(get(ARGS, 1, ""))
expected_version = get(ARGS, 2, "")
isempty(String(package_name)) && error("package name is required")
isempty(expected_version) && error("expected package version is required")
target_module = Base.require(Main, package_name)
actual_version = string(pkgversion(target_module))
actual_version == expected_version || error(
    "$(package_name) version mismatch: expected $(expected_version), loaded $(actual_version)",
)
println("$(package_name)=$(actual_version)")
