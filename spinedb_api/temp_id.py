######################################################################################################################
# Copyright (C) 2017-2022 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################
"""
Temp id stuff.

"""


class TempId(int):
    _next_id = {}

    def __new__(cls, item_type):
        id_ = cls._next_id.setdefault(item_type, -1)
        cls._next_id[item_type] -= 1
        return super().__new__(cls, id_)

    def __init__(self, item_type):
        super().__init__()
        self._item_type = item_type
        self._value_binds = []
        self._tuple_value_binds = []
        self._key_binds = []
        self._tuple_key_binds = []

    def add_value_bind(self, item, key):
        self._value_binds.append((item, key))

    def add_tuple_value_bind(self, item, key):
        self._tuple_value_binds.append((item, key))

    def add_key_bind(self, item):
        self._key_binds.append(item)

    def add_tuple_key_bind(self, item, key):
        self._tuple_key_binds.append((item, key))

    def remove_key_bind(self, item):
        self._key_binds.remove(item)

    def remove_tuple_key_bind(self, item, key):
        self._tuple_key_binds.remove((item, key))

    def resolve(self, new_id):
        for item, key in self._value_binds:
            item[key] = new_id
        for item, key in self._tuple_value_binds:
            item[key] = tuple(new_id if v is self else v for v in item[key])
        for item in self._key_binds:
            if self in item:
                item[new_id] = dict.pop(item, self, None)
        for item, key in self._tuple_key_binds:
            if key in item:
                item[tuple(new_id if k is self else k for k in key)] = dict.pop(item, key, None)


class TempIdDict(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, value in kwargs.items():
            self._bind(key, value)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._bind(key, value)

    def __delitem__(self, key):
        super().__delitem__(key)
        self._unbind(key)

    def setdefault(self, key, default):
        value = super().setdefault(key, default)
        self._bind(key, value)
        return value

    def update(self, other):
        super().update(other)
        for key, value in other.items():
            self._bind(key, value)

    def pop(self, key, default):
        if key in self:
            self._unbind(key)
        return super().pop(key, default)

    def _bind(self, key, value):
        if isinstance(value, TempId):
            value.add_value_bind(self, key)
        elif isinstance(value, tuple):
            for v in value:
                if isinstance(v, TempId):
                    v.add_tuple_value_bind(self, key)
        elif isinstance(key, TempId):
            key.add_key_bind(self)
        elif isinstance(key, tuple):
            for k in key:
                if isinstance(k, TempId):
                    k.add_tuple_key_bind(self, key)

    def _unbind(self, key):
        if isinstance(key, TempId):
            key.remove_key_bind(self)
        elif isinstance(key, tuple):
            for k in key:
                if isinstance(k, TempId):
                    k.remove_tuple_key_bind(self, key)