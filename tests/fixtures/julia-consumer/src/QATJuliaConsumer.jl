"""Calculations used to qualify the Julia runner."""
module QATJuliaConsumer

export measured_total

"""
    measured_total(values)

Return the sum of the supplied integer samples.
"""
measured_total(values) = sum(values)

end
