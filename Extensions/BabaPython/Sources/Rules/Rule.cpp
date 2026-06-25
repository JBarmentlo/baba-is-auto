// Copyright (c) 2020-2026 Chris Ohk

// I am making my contributions/submissions to this project solely in our
// personal capacity and am not conveying any rights to any intellectual
// property of any third parties.

#include <Rules/Rule.hpp>
#include <baba-is-auto/Rules/Rule.hpp>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <tuple>

using namespace baba_is_auto;

void AddRule(pybind11::module& m)
{
    pybind11::class_<Rule>(m, "Rule")
        .def(pybind11::init<Object, Object, Object>())
        .def("__eq__",
             [](const Rule& left, const Rule& right) { return left == right; })
        // Exposes the rule's three objects (noun, verb, noun-or-property) so
        // callers can read a rule's contents from Python.
        .def_property_readonly(
            "objects",
            [](const Rule& rule) {
                return std::make_tuple(std::get<0>(rule.objects),
                                       std::get<1>(rule.objects),
                                       std::get<2>(rule.objects));
            });
}