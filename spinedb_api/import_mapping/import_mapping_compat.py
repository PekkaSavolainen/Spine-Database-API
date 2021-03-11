######################################################################################################################
# Copyright (C) 2017-2021 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Classes for item import mappings.

:author: P. Vennström (VTT)
:date:   22.02.2018
"""
from ..spine_io.mapping import (
    ObjectClassMapping,
    ObjectMapping,
    ParameterDefinitionMapping,
    ParameterValueMapping,
    ParameterValueTypeMapping,
    ParameterValueIndexMapping,
    ExpandedParameterValueMapping,
    Position,
)


def import_mapping_from_dict(map_dict):
    """Creates Mapping object from a dict"""
    if not isinstance(map_dict, dict):
        raise TypeError(f"map_dict must be a dict, instead it was: {type(map_dict)}")
    map_type = map_dict.get("map_type")
    legacy_mapping_from_dict = {
        "ObjectClass": _object_class_mapping_from_dict,
        # AlternativeImportMapping,
        # FeatureImportMapping,
        # ObjectGroupImportMapping,
        # ParameterValueListImportMapping,
        # RelationshipClassImportMapping,
        # ScenarioAlternativeImportMapping,
        # ScenarioImportMapping,
        # ToolFeatureImportMapping,
        # ToolFeatureMethodImportMapping,
        # ToolImportMapping,
    }
    from_dict = legacy_mapping_from_dict.get(map_type)
    if from_dict is not None:
        return from_dict(map_dict)
    raise ValueError(f'invalid "map_type" value, expected any of {", ".join(legacy_mapping_from_dict)}, got {map_type}')


def _object_class_mapping_from_dict(map_dict):
    name = map_dict.get("name")
    objects = map_dict.get("objects")
    if objects is None:
        # Previous versions saved "object" instead of "objects"
        objects = map_dict.get("object", None)
    root_mapping = ObjectClassMapping(*_pos_and_val(name))
    object_mapping = root_mapping.child = ObjectMapping(*_pos_and_val(objects))
    parameters = map_dict.get("parameters")
    object_mapping.child = _parameter_mapping_from_dict(parameters)
    return root_mapping
    # FIXME: We need to handle this below too:
    # object_metadata = map_dict.get("object_metadata", None)
    # skip_columns = map_dict.get("skip_columns", [])
    # read_start_row = map_dict.get("read_start_row", 0)


def _parameter_mapping_from_dict(map_dict):
    if map_dict is None:
        return None
    map_type = map_dict.get("map_type")
    if map_type == "parameter" or "parameter_type" in map_dict:
        _fix_parameter_mapping_dict(map_dict)
    map_type = map_dict.get("map_type")
    if map_type == "None":
        return None
    param_def_mapping = ParameterDefinitionMapping(*_pos_and_val(map_dict["name"]))
    if map_type == "ParameterDefinition":
        return param_def_mapping
    value_dict = map_dict["value"]
    value_type = value_dict["value_type"]
    if value_type == "single value":
        param_def_mapping.child = ParameterValueMapping(*_pos_and_val(value_dict["main_value"]))
        return param_def_mapping
    extra_dimensions = value_dict.get("extra_dimensions", [None])
    value_type = value_type.replace(" ", "_")
    param_def_mapping.child = parent_mapping = ParameterValueTypeMapping(Position.hidden, value_type)
    for ed in extra_dimensions:
        mapping = ParameterValueIndexMapping(*_pos_and_val(ed))
        parent_mapping.child = mapping
        parent_mapping = mapping
    parent_mapping.child = ExpandedParameterValueMapping(*_pos_and_val(value_dict["main_value"]))
    return param_def_mapping


def _fix_parameter_mapping_dict(map_dict):
    # Even deeper legacy
    parameter_type = map_dict.pop("parameter_type", None)
    if parameter_type == "definition":
        map_dict["map_type"] = "ParameterDefinition"
    else:
        value_dict = map_dict.copy()
        value_dict.pop("name", None)
        value_dict["value_type"] = parameter_type if parameter_type else "single value"
        value_dict["main_value"] = value_dict.pop("value", None)
        map_dict["map_type"] = "ParameterValue"
        map_dict["value"] = value_dict


def _pos_and_val(x):
    if not isinstance(x, dict):
        map_type = "constant" if isinstance(x, str) else "column"
        map_dict = {"map_type": map_type, "reference": x}
    else:
        map_dict = x
    map_type = map_dict.get("map_type")
    ref = map_dict.get("reference", map_dict.get("value_reference"))
    if isinstance(ref, str) and not ref:
        ref = None
    # None, or invalid reference
    if map_type == "None" or ref is None:
        return Position.hidden, None  # This combination disables the mapping
    # Constant
    if map_type == "constant":
        if not isinstance(ref, str):
            raise TypeError(f"Constant reference must be str, instead got: {type(ref).__name__}")
        return Position.hidden, ref
    # Table name
    if map_type == "table_name":
        return Position.table_name, None
    # Row or column reference, including header
    if not isinstance(ref, (str, int)):
        raise TypeError(f"Row or column reference must be str or int, instead got: {type(ref).__name__}")
    # 1. Column header
    if map_type in ("column_name", "column_header"):
        if isinstance(ref, int) and ref < 0:
            ref = 0
        return Position.header, ref
    # 2. Data row or column
    try:
        ref = int(ref)
    except ValueError:
        pass
    # 2a. Column
    if map_type == "column":
        if isinstance(ref, int) and ref < 0:
            ref = 0
        return ref, None
    # 2b. Row
    if map_type == "row":
        if isinstance(ref, int):
            if ref == -1:
                return Position.header, None
            if ref < -1:
                ref = 0
            return -(ref + 1), None  # pylint: disable=invalid-unary-operand-type
        if ref.lower() == "header":
            return Position.header, None
        raise ValueError(f"If row reference is str, it must be 'header'. Instead got '{ref}'")
    # Fallback to invalid
    return Position.hidden, None
