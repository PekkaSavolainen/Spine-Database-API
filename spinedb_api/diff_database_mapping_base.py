######################################################################################################################
# Copyright (C) 2017 - 2019 Spine project consortium
# This file is part of Spine Database API.
# Spine Database API is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser
# General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Provides :class:`.DiffDatabaseMappingBase`.

:author: Manuel Marin (KTH)
:date:   11.8.2018
"""

from .database_mapping_base import DatabaseMappingBase
from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.sql.expression import Alias
from .exception import SpineTableNotFoundError
from .helpers import forward_sweep
from datetime import datetime, timezone
from sqlalchemy.orm.util import AliasedInsp

# TODO: improve docstrings


class DiffDatabaseMappingBase(DatabaseMappingBase):
    """Base class for the read-write database mapping.

    :param str db_url: A URL in RFC-1738 format pointing to the database to be mapped.
    :param str username: A user name. If ``None``, it gets replaced by the string ``"anon"``.
    :param bool upgrade: Whether or not the db at the given URL should be upgraded to the most recent version.
    """

    # NOTE: It works by creating and mapping a set of
    # temporary 'diff' tables, where temporary changes are staged until the moment of commit.

    def __init__(self, *args, **kwargs):
        """Initialize class."""
        super().__init__(*args, **kwargs)
        self.diff_prefix = None
        # Diff classes
        self.DiffCommit = None
        self.DiffEntityClass = None
        self.DiffEntityClassType = None
        self.DiffEntity = None
        self.DiffEntityType = None
        self.DiffObject = None
        self.DiffObjectClass = None
        self.DiffRelationshipClass = None
        self.DiffRelationshipEntityClass = None
        self.DiffRelationship = None
        self.DiffRelationshipEntity = None
        self.DiffParameterDefinition = None
        self.DiffParameterValue = None
        self.DiffParameterTag = None
        self.DiffParameterDefinitionTag = None
        self.DiffParameterValueList = None
        # Diff dictionaries
        self.added_item_id = {}
        self.updated_item_id = {}
        self.removed_item_id = {}
        self.dirty_item_id = {}
        # Initialize stuff
        self._init_diff_dicts()
        self._create_diff_tables_and_mapping()

    def _init_diff_dicts(self):
        """Initialize dictionaries that help keeping track of the differences."""
        self.added_item_id = {x: set() for x in self.table_to_class}
        self.updated_item_id = {x: set() for x in self.table_to_class}
        self.removed_item_id = {x: set() for x in self.table_to_class}
        self.dirty_item_id = {x: set() for x in self.table_to_class}
        self._clear_subqueries(*self.table_to_class)

    def _create_diff_tables_and_mapping(self):
        """Create diff tables and ORM."""
        # Create tables...
        diff_name_prefix = "diff_" + self.username
        self.diff_prefix = diff_name_prefix + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_"
        metadata = MetaData(self.engine)
        metadata.reflect()
        diff_metadata = MetaData()
        diff_tables = list()
        for t in metadata.sorted_tables:
            if t.name.startswith(diff_name_prefix) or t.name == "next_id":
                continue
            diff_columns = [c.copy() for c in t.columns]
            diff_table = Table(self.diff_prefix + t.name, diff_metadata, *diff_columns, prefixes=["TEMPORARY"])
        diff_metadata.drop_all(self.engine)
        # NOTE: Using `self.connection` below allows `self.session` to see the temp tables
        diff_metadata.create_all(self.connection)
        # Create mapping...
        DiffBase = automap_base(metadata=diff_metadata)
        DiffBase.prepare()
        not_found = []
        for tablename, classname in self.table_to_class.items():
            try:
                setattr(self, "Diff" + classname, getattr(DiffBase.classes, self.diff_prefix + tablename))
            except (NoSuchTableError, AttributeError):
                not_found.append(tablename)
        if not_found:
            raise SpineTableNotFoundError(not_found, self.db_url)

    def _mark_as_dirty(self, tablename, ids):
        """Mark items as dirty, which means the corresponding records from the original tables
        are no longer valid, and they should be queried from the diff tables instead."""
        self.dirty_item_id[tablename].update(ids)
        self._clear_subqueries(tablename)

    def _clear_subqueries(self, *tablenames):
        """Set to `None` subquery attributes involving the affected tables.
        This forces the subqueries to be refreshed when accessing the corresponding property.
        """
        for attr, val in self.__dict__.items():
            if not isinstance(val, Alias):
                continue
            tables = []
            func = lambda x: isinstance(x, Table) and tables.append(x.name)
            forward_sweep(val, func)
            # Now `tables` contains all tables related to `val`
            if any(t in tables for t in tablenames):
                setattr(self, attr, None)

    def _subquery(self, tablename):
        """Overriden method to
            (i) filter dirty items from original tables, and
            (ii) also bring data from diff tables:
        Roughly equivalent to:
            SELECT * FROM orig_table WHERE id NOT IN dirty_ids
            UNION ALL
            SELECT * FROM diff_table
        """
        classname = self.table_to_class[tablename]
        orig_class = getattr(self, classname)
        diff_class = getattr(self, "Diff" + classname)
        id_col = self.table_ids.get(tablename, "id")
        return (
            self.query(*[c.label(c.name) for c in inspect(orig_class).mapper.columns])
            .filter(~getattr(orig_class, id_col).in_(self.dirty_item_id[tablename]))
            .union_all(self.query(*inspect(diff_class).mapper.columns))
            .subquery()
        )

    def _reset_diff_mapping(self):
        """Delete all records from diff tables (but don't drop the tables)."""
        self.query(self.DiffEntityClass).delete()
        self.query(self.DiffEntity).delete()
        self.query(self.DiffRelationshipClass).delete()
        self.query(self.DiffRelationship).delete()
        self.query(self.DiffParameterDefinition).delete()
        self.query(self.DiffParameterValue).delete()
        self.query(self.DiffParameterTag).delete()
        self.query(self.DiffParameterDefinitionTag).delete()
        self.query(self.DiffParameterValueList).delete()
        self.query(self.DiffObject).delete()
        self.query(self.DiffObjectClass).delete()
        self.query(self.DiffRelationshipEntityClass).delete()
        self.query(self.DiffRelationshipEntity).delete()