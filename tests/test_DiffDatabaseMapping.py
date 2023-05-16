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
Unit tests for DatabaseMapping class.

"""

import os.path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from sqlalchemy.engine.url import make_url, URL
from sqlalchemy.util import KeyedTuple
from spinedb_api.db_mapping import DatabaseMapping
from spinedb_api.exception import SpineIntegrityError
from spinedb_api import import_functions, SpineDBAPIError


def create_query_wrapper(db_map):
    def query_wrapper(*args, orig_query=db_map.query, **kwargs):
        arg = args[0]
        if isinstance(arg, mock.Mock):
            return arg.value
        return orig_query(*args, **kwargs)

    return query_wrapper


IN_MEMORY_DB_URL = "sqlite://"


def create_diff_db_map():
    return DatabaseMapping(IN_MEMORY_DB_URL, username="UnitTest", create=True)


class TestDatabaseMappingConstruction(unittest.TestCase):
    def test_construction_with_filters(self):
        db_url = IN_MEMORY_DB_URL + "?spinedbfilter=fltr1&spinedbfilter=fltr2"
        with mock.patch("spinedb_api.db_mapping.apply_filter_stack") as mock_apply:
            with mock.patch(
                "spinedb_api.db_mapping.load_filters", return_value=[{"fltr1": "config1", "fltr2": "config2"}]
            ) as mock_load:
                db_map = DatabaseMapping(db_url, create=True)
                db_map.connection.close()
                mock_load.assert_called_once_with(["fltr1", "fltr2"])
                mock_apply.assert_called_once_with(db_map, [{"fltr1": "config1", "fltr2": "config2"}])

    def test_construction_with_sqlalchemy_url_and_filters(self):
        db_url = IN_MEMORY_DB_URL + "/?spinedbfilter=fltr1&spinedbfilter=fltr2"
        sa_url = make_url(db_url)
        with mock.patch("spinedb_api.db_mapping.apply_filter_stack") as mock_apply:
            with mock.patch(
                "spinedb_api.db_mapping.load_filters", return_value=[{"fltr1": "config1", "fltr2": "config2"}]
            ) as mock_load:
                db_map = DatabaseMapping(sa_url, create=True)
                db_map.connection.close()
                mock_load.assert_called_once_with(["fltr1", "fltr2"])
                mock_apply.assert_called_once_with(db_map, [{"fltr1": "config1", "fltr2": "config2"}])

    def test_shorthand_filter_query_works(self):
        with TemporaryDirectory() as temp_dir:
            url = URL("sqlite")
            url.database = os.path.join(temp_dir, "test_shorthand_filter_query_works.json")
            out_db = DatabaseMapping(url, create=True)
            out_db.add_scenarios({"name": "scen1"})
            out_db.add_scenario_alternatives({"scenario_name": "scen1", "alternative_name": "Base", "rank": 1})
            out_db.commit_session("Add scen.")
            out_db.connection.close()
            try:
                db_map = DatabaseMapping(url)
            except:
                self.fail("DatabaseMapping.__init__() should not raise.")
            else:
                db_map.connection.close()


class TestDatabaseMappingRemove(unittest.TestCase):
    def setUp(self):
        self._db_map = create_diff_db_map()

    def tearDown(self):
        self._db_map.connection.close()

    def test_cascade_remove_relationship(self):
        """Test adding and removing a relationship and committing"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 2})
        items, _ = self._db_map.add_wide_relationships(
            {"id": 3, "name": "remove_me", "class_id": 3, "object_id_list": [1, 2]}
        )
        self._db_map.remove_items("relationship", *{x["id"] for x in items})
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_sq).all()), 0)
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_sq).all()), 0)

    def test_cascade_remove_relationship_from_committed_session(self):
        """Test removing a relationship from a committed session"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 2})
        items, _ = self._db_map.add_wide_relationships(
            {"id": 3, "name": "remove_me", "class_id": 3, "object_id_list": [1, 2]}
        )
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_sq).all()), 1)
        self._db_map.remove_items("relationship", *{x["id"] for x in items})
        self._db_map.commit_session("Add test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_sq).all()), 0)

    def test_remove_object(self):
        """Test adding and removing an object and committing"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        items, _ = self._db_map.add_objects(
            {"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 2}
        )
        self._db_map.remove_items("object", *{x["id"] for x in items})
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.object_sq).all()), 0)

    def test_remove_object_from_committed_session(self):
        """Test removing an object from a committed session"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        items, _ = self._db_map.add_objects(
            {"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 2}
        )
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.object_sq).all()), 2)
        self._db_map.remove_items("object", *{x["id"] for x in items})
        self._db_map.commit_session("Add test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.object_sq).all()), 0)

    def test_remove_entity_group(self):
        """Test adding and removing an entity group and committing"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        items, _ = self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 1, "member_id": 2})
        self._db_map.remove_items("entity_group", *{x["id"] for x in items})
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.entity_group_sq).all()), 0)

    def test_remove_entity_group_from_committed_session(self):
        """Test removing an entity group from a committed session"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 1, "member_id": 2})
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.entity_group_sq).all()), 1)
        self._db_map.remove_items("entity_group", 1)
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.entity_group_sq).all()), 0)

    def test_cascade_remove_relationship_class(self):
        """Test adding and removing a relationship class and committing"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        items, _ = self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.remove_items("relationship_class", *{x["id"] for x in items})
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_class_sq).all()), 0)

    def test_cascade_remove_relationship_class_from_committed_session(self):
        """Test removing a relationship class from a committed session"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        items, _ = self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_class_sq).all()), 1)
        self._db_map.remove_items("relationship_class", *{x["id"] for x in items})
        self._db_map.commit_session("remove")
        self.assertEqual(len(self._db_map.query(self._db_map.wide_relationship_class_sq).all()), 0)

    def test_remove_object_class(self):
        """Test adding and removing an object class and committing"""
        items, _ = self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.remove_items("object_class", *{x["id"] for x in items})
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.object_class_sq).all()), 0)

    def test_remove_object_class_from_committed_session(self):
        """Test removing an object class from a committed session"""
        items, _ = self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.object_class_sq).all()), 2)
        self._db_map.remove_items("object_class", *{x["id"] for x in items})
        self._db_map.commit_session("Add test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.object_class_sq).all()), 0)

    def test_remove_parameter_value(self):
        """Test adding and removing a parameter value and committing"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, strict=True)
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, strict=True)
        self._db_map.add_parameter_definitions({"name": "param", "id": 1, "object_class_id": 1}, strict=True)
        self._db_map.add_parameter_values(
            {
                "value": b"0",
                "id": 1,
                "parameter_definition_id": 1,
                "object_id": 1,
                "object_class_id": 1,
                "alternative_id": 1,
            },
            strict=True,
        )
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 1)
        self._db_map.remove_items("parameter_value", 1)
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 0)

    def test_remove_parameter_value_from_committed_session(self):
        """Test adding and committing a parameter value and then removing it"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, strict=True)
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, strict=True)
        self._db_map.add_parameter_definitions({"name": "param", "id": 1, "object_class_id": 1}, strict=True)
        self._db_map.add_parameter_values(
            {
                "value": b"0",
                "id": 1,
                "parameter_definition_id": 1,
                "object_id": 1,
                "object_class_id": 1,
                "alternative_id": 1,
            },
            strict=True,
        )
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 1)
        self._db_map.remove_items("parameter_value", 1)
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 0)

    def test_cascade_remove_object_removes_parameter_value_as_well(self):
        """Test adding and removing a parameter value and committing"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, strict=True)
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, strict=True)
        self._db_map.add_parameter_definitions({"name": "param", "id": 1, "object_class_id": 1}, strict=True)
        self._db_map.add_parameter_values(
            {
                "value": b"0",
                "id": 1,
                "parameter_definition_id": 1,
                "object_id": 1,
                "object_class_id": 1,
                "alternative_id": 1,
            },
            strict=True,
        )
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 1)
        self._db_map.remove_items("object", 1)
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 0)

    def test_cascade_remove_object_from_committed_session_removes_parameter_value_as_well(self):
        """Test adding and committing a paramater value and then removing it"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, strict=True)
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, strict=True)
        self._db_map.add_parameter_definitions({"name": "param", "id": 1, "object_class_id": 1}, strict=True)
        self._db_map.add_parameter_values(
            {
                "value": b"0",
                "id": 1,
                "parameter_definition_id": 1,
                "object_id": 1,
                "object_class_id": 1,
                "alternative_id": 1,
            },
            strict=True,
        )
        self._db_map.commit_session("add")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 1)
        self._db_map.remove_items("object", 1)
        self._db_map.commit_session("delete")
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 0)

    def test_cascade_remove_metadata_removes_corresponding_entity_and_value_metadata(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        import_functions.import_objects(self._db_map, (("my_class", "my_object"),))
        import_functions.import_object_parameters(self._db_map, (("my_class", "my_parameter"),))
        import_functions.import_object_parameter_values(
            self._db_map, (("my_class", "my_object", "my_parameter", 99.0),)
        )
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_object_metadata(self._db_map, (("my_class", "my_object", '{"title": "My metadata."}'),))
        import_functions.import_object_parameter_value_metadata(
            self._db_map, (("my_class", "my_object", "my_parameter", '{"title": "My metadata."}'),)
        )
        self._db_map.commit_session("Add test data.")
        metadata = self._db_map.query(self._db_map.metadata_sq).all()
        self.assertEqual(len(metadata), 1)
        self._db_map.remove_items("metadata", metadata[0].id)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.object_sq).all()), 1)
        self.assertEqual(len(self._db_map.query(self._db_map.object_parameter_definition_sq).all()), 1)

    def test_cascade_remove_entity_metadata_removes_corresponding_metadata(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        import_functions.import_objects(self._db_map, (("my_class", "my_object"),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_object_metadata(self._db_map, (("my_class", "my_object", '{"title": "My metadata."}'),))
        self._db_map.commit_session("Add test data.")
        entity_metadata = self._db_map.query(self._db_map.entity_metadata_sq).all()
        self.assertEqual(len(entity_metadata), 1)
        self._db_map.remove_items("entity_metadata", entity_metadata[0].id)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.object_sq).all()), 1)

    def test_cascade_remove_entity_metadata_leaves_metadata_used_by_value_intact(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        import_functions.import_objects(self._db_map, (("my_class", "my_object"),))
        import_functions.import_object_parameters(self._db_map, (("my_class", "my_parameter"),))
        import_functions.import_object_parameter_values(
            self._db_map, (("my_class", "my_object", "my_parameter", 99.0),)
        )
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_object_metadata(self._db_map, (("my_class", "my_object", '{"title": "My metadata."}'),))
        import_functions.import_object_parameter_value_metadata(
            self._db_map, (("my_class", "my_object", "my_parameter", '{"title": "My metadata."}'),)
        )
        self._db_map.commit_session("Add test data.")
        entity_metadata = self._db_map.query(self._db_map.entity_metadata_sq).all()
        self.assertEqual(len(entity_metadata), 1)
        self._db_map.remove_items("entity_metadata", entity_metadata[0].id)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 1)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_metadata_sq).all()), 1)

    def test_cascade_remove_value_metadata_leaves_metadata_used_by_entity_intact(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        import_functions.import_objects(self._db_map, (("my_class", "my_object"),))
        import_functions.import_object_parameters(self._db_map, (("my_class", "my_parameter"),))
        import_functions.import_object_parameter_values(
            self._db_map, (("my_class", "my_object", "my_parameter", 99.0),)
        )
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_object_metadata(self._db_map, (("my_class", "my_object", '{"title": "My metadata."}'),))
        import_functions.import_object_parameter_value_metadata(
            self._db_map, (("my_class", "my_object", "my_parameter", '{"title": "My metadata."}'),)
        )
        self._db_map.commit_session("Add test data.")
        parameter_value_metadata = self._db_map.query(self._db_map.parameter_value_metadata_sq).all()
        self.assertEqual(len(parameter_value_metadata), 1)
        self._db_map.remove_items("parameter_value_metadata", parameter_value_metadata[0].id)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 1)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 1)
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_metadata_sq).all()), 0)

    def test_cascade_remove_object_removes_its_metadata(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        import_functions.import_objects(self._db_map, (("my_class", "my_object"),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_object_metadata(self._db_map, (("my_class", "my_object", '{"title": "My metadata."}'),))
        self._db_map.commit_session("Add test data.")
        self._db_map.remove_items("object", 1)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.object_sq).all()), 0)

    def test_cascade_remove_relationship_removes_its_metadata(self):
        import_functions.import_object_classes(self._db_map, ("my_object_class",))
        import_functions.import_objects(self._db_map, (("my_object_class", "my_object"),))
        import_functions.import_relationship_classes(self._db_map, (("my_class", ("my_object_class",)),))
        import_functions.import_relationships(self._db_map, (("my_class", ("my_object",)),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_relationship_metadata(
            self._db_map, (("my_class", ("my_object",), '{"title": "My metadata."}'),)
        )
        self._db_map.commit_session("Add test data.")
        self._db_map.remove_items("relationship", 2)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.relationship_sq).all()), 0)

    def test_cascade_remove_parameter_value_removes_its_metadata(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        import_functions.import_objects(self._db_map, (("my_class", "my_object"),))
        import_functions.import_object_parameters(self._db_map, (("my_class", "my_parameter"),))
        import_functions.import_object_parameter_values(
            self._db_map, (("my_class", "my_object", "my_parameter", 99.0),)
        )
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        import_functions.import_object_parameter_value_metadata(
            self._db_map, (("my_class", "my_object", "my_parameter", '{"title": "My metadata."}'),)
        )
        self._db_map.commit_session("Add test data.")
        self._db_map.remove_items("parameter_value", 1)
        self._db_map.commit_session("Remove test data.")
        self.assertEqual(len(self._db_map.query(self._db_map.metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.entity_metadata_sq).all()), 0)
        self.assertEqual(len(self._db_map.query(self._db_map.parameter_value_sq).all()), 0)


class TestDatabaseMappingAdd(unittest.TestCase):
    def setUp(self):
        self._db_map = create_diff_db_map()

    def tearDown(self):
        self._db_map.connection.close()

    def test_add_and_retrieve_many_objects(self):
        """Tests add many objects into db and retrieving them."""
        items, _ = self._db_map.add_object_classes({"name": "testclass"})
        class_id = next(iter(items))["id"]
        added = self._db_map.add_objects(*[{"name": str(i), "class_id": class_id} for i in range(1001)])[0]
        self.assertEqual(len(added), 1001)
        self._db_map.commit_session("test_commit")
        self.assertEqual(self._db_map.query(self._db_map.entity_sq).count(), 1001)

    def test_add_object_classes(self):
        """Test that adding object classes works."""
        self._db_map.add_object_classes({"name": "fish"}, {"name": "dog"})
        self._db_map.commit_session("add")
        object_classes = self._db_map.query(self._db_map.object_class_sq).all()
        self.assertEqual(len(object_classes), 2)
        self.assertEqual(object_classes[0].name, "fish")
        self.assertEqual(object_classes[1].name, "dog")

    def test_add_object_class_with_invalid_name(self):
        """Test that adding object classes with empty name raises error"""
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_object_classes({"name": ""}, strict=True)

    def test_add_object_classes_with_same_name(self):
        """Test that adding two object classes with the same name only adds one of them."""
        self._db_map.add_object_classes({"name": "fish"}, {"name": "fish"})
        self._db_map.commit_session("add")
        object_classes = self._db_map.query(self._db_map.object_class_sq).all()
        self.assertEqual(len(object_classes), 1)
        self.assertEqual(object_classes[0].name, "fish")

    def test_add_object_class_with_same_name_as_existing_one(self):
        """Test that adding an object class with an already taken name raises an integrity error."""
        self._db_map.add_object_classes({"name": "fish"}, {"name": "fish"})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_object_classes({"name": "fish"}, strict=True)

    def test_add_objects(self):
        """Test that adding objects works."""
        self._db_map.add_object_classes({"name": "fish", "id": 1})
        self._db_map.add_objects({"name": "nemo", "class_id": 1}, {"name": "dory", "class_id": 1})
        self._db_map.commit_session("add")
        objects = self._db_map.query(self._db_map.object_sq).all()
        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0].name, "nemo")
        self.assertEqual(objects[0].class_id, 1)
        self.assertEqual(objects[1].name, "dory")
        self.assertEqual(objects[1].class_id, 1)

    def test_add_object_with_invalid_name(self):
        """Test that adding object classes with empty name raises error"""
        self._db_map.add_object_classes({"name": "fish"})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_objects({"name": "", "class_id": 1}, strict=True)

    def test_add_objects_with_same_name(self):
        """Test that adding two objects with the same name only adds one of them."""
        self._db_map.add_object_classes({"name": "fish", "id": 1})
        self._db_map.add_objects({"name": "nemo", "class_id": 1}, {"name": "nemo", "class_id": 1})
        self._db_map.commit_session("add")
        objects = self._db_map.query(self._db_map.object_sq).all()
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].name, "nemo")
        self.assertEqual(objects[0].class_id, 1)

    def test_add_object_with_same_name_as_existing_one(self):
        """Test that adding an object with an already taken name raises an integrity error."""
        self._db_map.add_object_classes({"name": "fish"})
        self._db_map.add_objects({"name": "nemo", "class_id": 1})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_objects({"name": "nemo", "class_id": 1}, strict=True)

    def test_add_object_with_invalid_class(self):
        """Test that adding an object with a non existing class raises an integrity error."""
        self._db_map.add_object_classes({"name": "fish"})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_objects({"name": "pluto", "class_id": 2}, strict=True)

    def test_add_relationship_classes(self):
        """Test that adding relationship classes works."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes(
            {"name": "rc1", "object_class_id_list": [1, 2]}, {"name": "rc2", "object_class_id_list": [2, 1]}
        )
        self._db_map.commit_session("add")
        table = self._db_map.get_table("entity_class_dimension")
        ent_cls_dims = self._db_map.query(table).all()
        rel_clss = self._db_map.query(self._db_map.wide_relationship_class_sq).all()
        self.assertEqual(len(ent_cls_dims), 4)
        self.assertEqual(rel_clss[0].name, "rc1")
        self.assertEqual(ent_cls_dims[0].dimension_id, 1)
        self.assertEqual(ent_cls_dims[1].dimension_id, 2)
        self.assertEqual(rel_clss[1].name, "rc2")
        self.assertEqual(ent_cls_dims[2].dimension_id, 2)
        self.assertEqual(ent_cls_dims[3].dimension_id, 1)

    def test_add_relationship_classes_with_invalid_name(self):
        """Test that adding object classes with empty name raises error"""
        self._db_map.add_object_classes({"name": "fish"})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_wide_relationship_classes({"name": "", "object_class_id_list": [1]}, strict=True)

    def test_add_relationship_classes_with_same_name(self):
        """Test that adding two relationship classes with the same name only adds one of them."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes(
            {"name": "rc1", "object_class_id_list": [1, 2]},
            {"name": "rc1", "object_class_id_list": [1, 2]},
            strict=False,
        )
        self._db_map.commit_session("add")
        table = self._db_map.get_table("entity_class_dimension")
        ecs_dims = self._db_map.query(table).all()
        relationship_classes = self._db_map.query(self._db_map.wide_relationship_class_sq).all()
        self.assertEqual(len(ecs_dims), 2)
        self.assertEqual(len(relationship_classes), 1)
        self.assertEqual(relationship_classes[0].name, "rc1")
        self.assertEqual(ecs_dims[0].dimension_id, 1)
        self.assertEqual(ecs_dims[1].dimension_id, 2)

    def test_add_relationship_class_with_same_name_as_existing_one(self):
        """Test that adding a relationship class with an already taken name raises an integrity error."""
        query_wrapper = create_query_wrapper(self._db_map)
        with mock.patch.object(DatabaseMapping, "query") as mock_query, mock.patch.object(
            DatabaseMapping, "object_class_sq"
        ) as mock_object_class_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_class_sq"
        ) as mock_wide_rel_cls_sq:
            mock_query.side_effect = query_wrapper
            mock_object_class_sq.return_value = [
                KeyedTuple([1, "fish"], labels=["id", "name"]),
                KeyedTuple([2, "dog"], labels=["id", "name"]),
            ]
            mock_wide_rel_cls_sq.return_value = [
                KeyedTuple([1, "1,2", "fish__dog"], labels=["id", "object_class_id_list", "name"])
            ]
            with self.assertRaises(SpineIntegrityError):
                self._db_map.add_wide_relationship_classes(
                    {"name": "fish__dog", "object_class_id_list": [1, 2]}, strict=True
                )

    def test_add_relationship_class_with_invalid_object_class(self):
        """Test that adding a relationship class with a non existing object class raises an integrity error."""
        query_wrapper = create_query_wrapper(self._db_map)
        with mock.patch.object(DatabaseMapping, "query") as mock_query, mock.patch.object(
            DatabaseMapping, "object_class_sq"
        ) as mock_object_class_sq, mock.patch.object(DatabaseMapping, "wide_relationship_class_sq"):
            mock_query.side_effect = query_wrapper
            mock_object_class_sq.return_value = [KeyedTuple([1, "fish"], labels=["id", "name"])]
            with self.assertRaises(SpineIntegrityError):
                self._db_map.add_wide_relationship_classes(
                    {"name": "fish__dog", "object_class_id_list": [1, 2]}, strict=True
                )

    def test_add_relationships(self):
        """Test that adding relationships works."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "object_class_id_list": [1, 2], "id": 3})
        self._db_map.add_objects({"name": "o1", "class_id": 1, "id": 1}, {"name": "o2", "class_id": 2, "id": 2})
        self._db_map.add_wide_relationships({"name": "nemo__pluto", "class_id": 3, "object_id_list": [1, 2]})
        self._db_map.commit_session("add")
        ent_els = self._db_map.query(self._db_map.get_table("entity_element")).all()
        relationships = self._db_map.query(self._db_map.wide_relationship_sq).all()
        self.assertEqual(len(ent_els), 2)
        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0].name, "nemo__pluto")
        self.assertEqual(ent_els[0].entity_class_id, 3)
        self.assertEqual(ent_els[0].element_id, 1)
        self.assertEqual(ent_els[1].entity_class_id, 3)
        self.assertEqual(ent_els[1].element_id, 2)

    def test_add_relationship_with_invalid_name(self):
        """Test that adding object classes with empty name raises error"""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, strict=True)
        self._db_map.add_wide_relationship_classes({"name": "rc1", "object_class_id_list": [1]}, strict=True)
        self._db_map.add_objects({"name": "o1", "class_id": 1}, strict=True)
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_wide_relationships({"name": "", "class_id": 2, "object_id_list": [1]}, strict=True)

    def test_add_identical_relationships(self):
        """Test that adding two relationships with the same class and same objects only adds the first one."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "object_class_id_list": [1, 2], "id": 3})
        self._db_map.add_objects({"name": "o1", "class_id": 1, "id": 1}, {"name": "o2", "class_id": 2, "id": 2})
        self._db_map.add_wide_relationships(
            {"name": "nemo__pluto", "class_id": 3, "object_id_list": [1, 2]},
            {"name": "nemo__pluto_duplicate", "class_id": 3, "object_id_list": [1, 2]},
        )
        self._db_map.commit_session("add")
        relationships = self._db_map.query(self._db_map.wide_relationship_sq).all()
        self.assertEqual(len(relationships), 1)

    def test_add_relationship_identical_to_existing_one(self):
        """Test that adding a relationship with the same class and same objects as an existing one
        raises an integrity error.
        """
        query_wrapper = create_query_wrapper(self._db_map)
        with mock.patch.object(DatabaseMapping, "query") as mock_query, mock.patch.object(
            DatabaseMapping, "object_sq"
        ) as mock_object_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_class_sq"
        ) as mock_wide_rel_cls_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_sq"
        ) as mock_wide_rel_sq:
            mock_query.side_effect = query_wrapper
            mock_object_sq.return_value = [
                KeyedTuple([1, 10, "nemo"], labels=["id", "class_id", "name"]),
                KeyedTuple([2, 20, "pluto"], labels=["id", "class_id", "name"]),
            ]
            mock_wide_rel_cls_sq.return_value = [
                KeyedTuple([1, "10,20", "fish__dog"], labels=["id", "object_class_id_list", "name"])
            ]
            mock_wide_rel_sq.return_value = [
                KeyedTuple([1, 1, "1,2", "nemo__pluto"], labels=["id", "class_id", "object_id_list", "name"])
            ]
            with self.assertRaises(SpineIntegrityError):
                self._db_map.add_wide_relationships(
                    {"name": "nemoy__plutoy", "class_id": 1, "object_id_list": [1, 2]}, strict=True
                )

    def test_add_relationship_with_invalid_class(self):
        """Test that adding a relationship with an invalid class raises an integrity error."""
        query_wrapper = create_query_wrapper(self._db_map)
        with mock.patch.object(DatabaseMapping, "query") as mock_query, mock.patch.object(
            DatabaseMapping, "object_sq"
        ) as mock_object_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_class_sq"
        ) as mock_wide_rel_cls_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_sq"
        ):
            mock_query.side_effect = query_wrapper
            mock_object_sq.return_value = [
                KeyedTuple([1, 10, "nemo"], labels=["id", "class_id", "name"]),
                KeyedTuple([2, 20, "pluto"], labels=["id", "class_id", "name"]),
            ]
            mock_wide_rel_cls_sq.return_value = [
                KeyedTuple([1, "10,20", "fish__dog"], labels=["id", "object_class_id_list", "name"])
            ]
            with self.assertRaises(SpineIntegrityError):
                self._db_map.add_wide_relationships(
                    {"name": "nemo__pluto", "class_id": 2, "object_id_list": [1, 2]}, strict=True
                )

    def test_add_relationship_with_invalid_object(self):
        """Test that adding a relationship with an invalid object raises an integrity error."""
        query_wrapper = create_query_wrapper(self._db_map)
        with mock.patch.object(DatabaseMapping, "query") as mock_query, mock.patch.object(
            DatabaseMapping, "object_sq"
        ) as mock_object_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_class_sq"
        ) as mock_wide_rel_cls_sq, mock.patch.object(
            DatabaseMapping, "wide_relationship_sq"
        ):
            mock_query.side_effect = query_wrapper
            mock_object_sq.return_value = [
                KeyedTuple([1, 10, "nemo"], labels=["id", "class_id", "name"]),
                KeyedTuple([2, 20, "pluto"], labels=["id", "class_id", "name"]),
            ]
            mock_wide_rel_cls_sq.return_value = [
                KeyedTuple([1, "10,20", "fish__dog"], labels=["id", "object_class_id_list", "name"])
            ]
            with self.assertRaises(SpineIntegrityError):
                self._db_map.add_wide_relationships(
                    {"name": "nemo__pluto", "class_id": 1, "object_id_list": [1, 3]}, strict=True
                )

    def test_add_entity_groups(self):
        """Test that adding group entities works."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 1, "member_id": 2})
        self._db_map.commit_session("add")
        table = self._db_map.get_table("entity_group")
        entity_groups = self._db_map.query(table).all()
        self.assertEqual(len(entity_groups), 1)
        self.assertEqual(entity_groups[0].entity_id, 1)
        self.assertEqual(entity_groups[0].entity_class_id, 1)
        self.assertEqual(entity_groups[0].member_id, 2)

    def test_add_entity_groups_with_invalid_class(self):
        """Test that adding group entities with an invalid class fails."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 2, "member_id": 2}, strict=True)

    def test_add_entity_groups_with_invalid_entity(self):
        """Test that adding group entities with an invalid entity fails."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_entity_groups({"entity_id": 3, "entity_class_id": 2, "member_id": 2}, strict=True)

    def test_add_entity_groups_with_invalid_member(self):
        """Test that adding group entities with an invalid member fails."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 2, "member_id": 3}, strict=True)

    def test_add_repeated_entity_groups(self):
        """Test that adding repeated group entities fails."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1})
        self._db_map.add_objects({"name": "o1", "id": 1, "class_id": 1}, {"name": "o2", "id": 2, "class_id": 1})
        self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 2, "member_id": 2})
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_entity_groups({"entity_id": 1, "entity_class_id": 2, "member_id": 2}, strict=True)

    def test_add_parameter_definitions(self):
        """Test that adding parameter definitions works."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.add_parameter_definitions(
            {"name": "color", "object_class_id": 1, "description": "test1"},
            {"name": "relative_speed", "relationship_class_id": 3, "description": "test2"},
        )
        self._db_map.commit_session("add")
        table = self._db_map.get_table("parameter_definition")
        parameter_definitions = self._db_map.query(table).all()
        self.assertEqual(len(parameter_definitions), 2)
        self.assertEqual(parameter_definitions[0].name, "color")
        self.assertEqual(parameter_definitions[0].entity_class_id, 1)
        self.assertEqual(parameter_definitions[0].description, "test1")
        self.assertEqual(parameter_definitions[1].name, "relative_speed")
        self.assertEqual(parameter_definitions[1].entity_class_id, 3)
        self.assertEqual(parameter_definitions[1].description, "test2")

    def test_add_parameter_with_invalid_name(self):
        """Test that adding object classes with empty name raises error"""
        self._db_map.add_object_classes({"name": "oc1"}, strict=True)
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_parameter_definitions({"name": "", "object_class_id": 1}, strict=True)

    def test_add_parameter_definitions_with_same_name(self):
        """Test that adding two parameter_definitions with the same name adds both of them."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.add_parameter_definitions(
            {"name": "color", "object_class_id": 1}, {"name": "color", "relationship_class_id": 3}
        )
        self._db_map.commit_session("add")
        table = self._db_map.get_table("parameter_definition")
        parameter_definitions = self._db_map.query(table).all()
        self.assertEqual(len(parameter_definitions), 2)
        self.assertEqual(parameter_definitions[0].name, "color")
        self.assertEqual(parameter_definitions[1].name, "color")
        self.assertEqual(parameter_definitions[0].entity_class_id, 1)

    def test_add_parameter_with_same_name_as_existing_one(self):
        """Test that adding parameter_definitions with an already taken name raises and integrity error."""
        self._db_map.add_object_classes({"name": "oc1", "id": 1}, {"name": "oc2", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "rc1", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.add_parameter_definitions(
            {"name": "color", "object_class_id": 1}, {"name": "color", "relationship_class_id": 3}
        )
        with self.assertRaises(SpineIntegrityError):
            self._db_map.add_parameter_definitions({"name": "color", "object_class_id": 1}, strict=True)

    def test_add_parameter_values(self):
        """Test that adding parameter values works."""
        import_functions.import_object_classes(self._db_map, ["fish", "dog"])
        import_functions.import_relationship_classes(self._db_map, [("fish_dog", ["fish", "dog"])])
        import_functions.import_objects(self._db_map, [("fish", "nemo"), ("dog", "pluto")])
        import_functions.import_relationships(self._db_map, [("fish_dog", ("nemo", "pluto"))])
        import_functions.import_object_parameters(self._db_map, [("fish", "color")])
        import_functions.import_relationship_parameters(self._db_map, [("fish_dog", "rel_speed")])
        self._db_map.commit_session("add")
        color_id = (
            self._db_map.query(self._db_map.parameter_definition_sq)
            .filter(self._db_map.parameter_definition_sq.c.name == "color")
            .first()
            .id
        )
        rel_speed_id = (
            self._db_map.query(self._db_map.parameter_definition_sq)
            .filter(self._db_map.parameter_definition_sq.c.name == "rel_speed")
            .first()
            .id
        )
        nemo_row = self._db_map.query(self._db_map.object_sq).filter(self._db_map.object_sq.c.name == "nemo").first()
        nemo__pluto_row = self._db_map.query(self._db_map.wide_relationship_sq).first()
        self._db_map.add_parameter_values(
            {
                "parameter_definition_id": color_id,
                "entity_id": nemo_row.id,
                "entity_class_id": nemo_row.class_id,
                "value": b'"orange"',
                "alternative_id": 1,
            },
            {
                "parameter_definition_id": rel_speed_id,
                "entity_id": nemo__pluto_row.id,
                "entity_class_id": nemo__pluto_row.class_id,
                "value": b"125",
                "alternative_id": 1,
            },
        )
        self._db_map.commit_session("add")
        table = self._db_map.get_table("parameter_value")
        parameter_values = self._db_map.query(table).all()
        self.assertEqual(len(parameter_values), 2)
        self.assertEqual(parameter_values[0].parameter_definition_id, 1)
        self.assertEqual(parameter_values[0].entity_id, 1)
        self.assertEqual(parameter_values[0].value, b'"orange"')
        self.assertEqual(parameter_values[1].parameter_definition_id, 2)
        self.assertEqual(parameter_values[1].entity_id, 3)
        self.assertEqual(parameter_values[1].value, b"125")

    def test_add_parameter_value_with_invalid_object_or_relationship(self):
        """Test that adding a parameter value with an invalid object or relationship raises an
        integrity error."""
        import_functions.import_object_classes(self._db_map, ["fish", "dog"])
        import_functions.import_relationship_classes(self._db_map, [("fish_dog", ["fish", "dog"])])
        import_functions.import_objects(self._db_map, [("fish", "nemo"), ("dog", "pluto")])
        import_functions.import_relationships(self._db_map, [("fish_dog", ("nemo", "pluto"))])
        import_functions.import_object_parameters(self._db_map, [("fish", "color")])
        import_functions.import_relationship_parameters(self._db_map, [("fish_dog", "rel_speed")])
        _, errors = self._db_map.add_parameter_values(
            {"parameter_definition_id": 1, "object_id": 3, "value": b'"orange"', "alternative_id": 1}, strict=False
        )
        self.assertEqual([str(e) for e in errors], ["invalid entity_class_id for parameter_value"])
        _, errors = self._db_map.add_parameter_values(
            {"parameter_definition_id": 2, "relationship_id": 2, "value": b"125", "alternative_id": 1}, strict=False
        )
        self.assertEqual([str(e) for e in errors], ["invalid entity_class_id for parameter_value"])

    def test_add_same_parameter_value_twice(self):
        """Test that adding a parameter value twice only adds the first one."""
        import_functions.import_object_classes(self._db_map, ["fish"])
        import_functions.import_objects(self._db_map, [("fish", "nemo")])
        import_functions.import_object_parameters(self._db_map, [("fish", "color")])
        self._db_map.commit_session("add")
        color_id = (
            self._db_map.query(self._db_map.parameter_definition_sq)
            .filter(self._db_map.parameter_definition_sq.c.name == "color")
            .first()
            .id
        )
        nemo_row = self._db_map.query(self._db_map.object_sq).filter(self._db_map.entity_sq.c.name == "nemo").first()
        self._db_map.add_parameter_values(
            {
                "parameter_definition_id": color_id,
                "entity_id": nemo_row.id,
                "entity_class_id": nemo_row.class_id,
                "value": b'"orange"',
                "alternative_id": 1,
            },
            {
                "parameter_definition_id": color_id,
                "entity_id": nemo_row.id,
                "entity_class_id": nemo_row.class_id,
                "value": b'"blue"',
                "alternative_id": 1,
            },
        )
        self._db_map.commit_session("add")
        table = self._db_map.get_table("parameter_value")
        parameter_values = self._db_map.query(table).all()
        self.assertEqual(len(parameter_values), 1)
        self.assertEqual(parameter_values[0].parameter_definition_id, 1)
        self.assertEqual(parameter_values[0].entity_id, 1)
        self.assertEqual(parameter_values[0].value, b'"orange"')

    def test_add_existing_parameter_value(self):
        """Test that adding an existing parameter value raises an integrity error."""
        import_functions.import_object_classes(self._db_map, ["fish"])
        import_functions.import_objects(self._db_map, [("fish", "nemo")])
        import_functions.import_object_parameters(self._db_map, [("fish", "color")])
        import_functions.import_object_parameter_values(self._db_map, [("fish", "nemo", "color", "orange")])
        self._db_map.commit_session("add")
        _, errors = self._db_map.add_parameter_values(
            {
                "parameter_definition_id": 1,
                "entity_class_id": 1,
                "entity_id": 1,
                "value": b'"blue"',
                "alternative_id": 1,
            },
            strict=False,
        )
        self.assertEqual(
            [str(e) for e in errors],
            [
                "there's already a parameter_value with "
                "{'parameter_definition_name': 'color', 'entity_byname': ('nemo',), 'alternative_name': 'Base'}"
            ],
        )

    def test_add_alternative(self):
        items, errors = self._db_map.add_alternatives({"name": "my_alternative"})
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add test data.")
        alternatives = self._db_map.query(self._db_map.alternative_sq).all()
        self.assertEqual(len(alternatives), 2)
        self.assertEqual(
            dict(alternatives[0]), {"id": 1, "name": "Base", "description": "Base alternative", "commit_id": 1}
        )
        self.assertEqual(
            dict(alternatives[1]), {"id": 2, "name": "my_alternative", "description": None, "commit_id": None}
        )

    def test_add_scenario(self):
        items, errors = self._db_map.add_scenarios({"name": "my_scenario"})
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add test data.")
        scenarios = self._db_map.query(self._db_map.scenario_sq).all()
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(
            dict(scenarios[0]),
            {"id": 1, "name": "my_scenario", "description": None, "active": False, "commit_id": None},
        )

    def test_add_scenario_alternative(self):
        import_functions.import_scenarios(self._db_map, ("my_scenario",))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_scenario_alternatives({"scenario_id": 1, "alternative_id": 1, "rank": 0})
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add test data.")
        scenario_alternatives = self._db_map.query(self._db_map.scenario_alternative_sq).all()
        self.assertEqual(len(scenario_alternatives), 1)
        self.assertEqual(
            dict(scenario_alternatives[0]),
            {"id": 1, "scenario_id": 1, "alternative_id": 1, "rank": 0, "commit_id": None},
        )

    def test_add_metadata(self):
        items, errors = self._db_map.add_metadata({"name": "test name", "value": "test_add_metadata"}, strict=False)
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add metadata")
        metadata = self._db_map.query(self._db_map.metadata_sq).all()
        self.assertEqual(len(metadata), 1)
        self.assertEqual(
            dict(metadata[0]), {"name": "test name", "id": 1, "value": "test_add_metadata", "commit_id": None}
        )

    def test_add_metadata_that_exists_does_not_add_it(self):
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        self._db_map.commit_session("Add test data.")
        items, _ = self._db_map.add_metadata({"name": "title", "value": "My metadata."}, strict=False)
        self.assertEqual(items, [])
        metadata = self._db_map.query(self._db_map.metadata_sq).all()
        self.assertEqual(len(metadata), 1)
        self.assertEqual(dict(metadata[0]), {"name": "title", "id": 1, "value": "My metadata.", "commit_id": None})

    def test_add_entity_metadata_for_object(self):
        import_functions.import_object_classes(self._db_map, ("fish",))
        import_functions.import_objects(self._db_map, (("fish", "leviathan"),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_entity_metadata({"entity_id": 1, "metadata_id": 1}, strict=False)
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add entity metadata")
        entity_metadata = self._db_map.query(self._db_map.ext_entity_metadata_sq).all()
        self.assertEqual(len(entity_metadata), 1)
        self.assertEqual(
            dict(entity_metadata[0]),
            {
                "entity_id": 1,
                "entity_name": "leviathan",
                "metadata_name": "title",
                "metadata_value": "My metadata.",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )

    def test_add_entity_metadata_for_relationship(self):
        import_functions.import_object_classes(self._db_map, ("my_object_class",))
        import_functions.import_objects(self._db_map, (("my_object_class", "my_object"),))
        import_functions.import_relationship_classes(self._db_map, (("my_relationship_class", ("my_object_class",)),))
        import_functions.import_relationships(self._db_map, (("my_relationship_class", ("my_object",)),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_entity_metadata({"entity_id": 2, "metadata_id": 1}, strict=False)
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add entity metadata")
        entity_metadata = self._db_map.query(self._db_map.ext_entity_metadata_sq).all()
        self.assertEqual(len(entity_metadata), 1)
        self.assertEqual(
            dict(entity_metadata[0]),
            {
                "entity_id": 2,
                "entity_name": "my_relationship_class_my_object",
                "metadata_name": "title",
                "metadata_value": "My metadata.",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )

    def test_add_entity_metadata_doesnt_raise_with_empty_cache(self):
        items, errors = self._db_map.add_entity_metadata({"entity_id": 1, "metadata_id": 1}, strict=False)
        self.assertEqual(items, [])
        self.assertEqual(len(errors), 1)

    def test_add_ext_entity_metadata_for_object(self):
        import_functions.import_object_classes(self._db_map, ("fish",))
        import_functions.import_objects(self._db_map, (("fish", "leviathan"),))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_ext_entity_metadata(
            {"entity_id": 1, "metadata_name": "key", "metadata_value": "object metadata"}, strict=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add entity metadata")
        entity_metadata = self._db_map.query(self._db_map.ext_entity_metadata_sq).all()
        self.assertEqual(len(entity_metadata), 1)
        self.assertEqual(
            dict(entity_metadata[0]),
            {
                "entity_id": 1,
                "entity_name": "leviathan",
                "metadata_name": "key",
                "metadata_value": "object metadata",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )

    def test_adding_ext_entity_metadata_for_object_reuses_existing_metadata_names_and_values(self):
        import_functions.import_object_classes(self._db_map, ("fish",))
        import_functions.import_objects(self._db_map, (("fish", "leviathan"),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_ext_entity_metadata(
            {"entity_id": 1, "metadata_name": "title", "metadata_value": "My metadata."}, strict=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add entity metadata")
        metadata = self._db_map.query(self._db_map.metadata_sq).all()
        self.assertEqual(len(metadata), 1)
        self.assertEqual(dict(metadata[0]), {"id": 1, "name": "title", "value": "My metadata.", "commit_id": None})
        entity_metadata = self._db_map.query(self._db_map.ext_entity_metadata_sq).all()
        self.assertEqual(len(entity_metadata), 1)
        self.assertEqual(
            dict(entity_metadata[0]),
            {
                "entity_id": 1,
                "entity_name": "leviathan",
                "metadata_name": "title",
                "metadata_value": "My metadata.",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )

    def test_add_parameter_value_metadata(self):
        import_functions.import_object_classes(self._db_map, ("fish",))
        import_functions.import_objects(self._db_map, (("fish", "leviathan"),))
        import_functions.import_object_parameters(self._db_map, (("fish", "paranormality"),))
        import_functions.import_object_parameter_values(self._db_map, (("fish", "leviathan", "paranormality", 3.9),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_parameter_value_metadata(
            {"parameter_value_id": 1, "metadata_id": 1, "alternative_id": 1}, strict=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add value metadata")
        value_metadata = self._db_map.query(self._db_map.ext_parameter_value_metadata_sq).all()
        self.assertEqual(len(value_metadata), 1)
        self.assertEqual(
            dict(value_metadata[0]),
            {
                "alternative_name": "Base",
                "entity_name": "leviathan",
                "parameter_value_id": 1,
                "parameter_name": "paranormality",
                "metadata_name": "title",
                "metadata_value": "My metadata.",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )

    def test_add_parameter_value_metadata_doesnt_raise_with_empty_cache(self):
        items, errors = self._db_map.add_parameter_value_metadata(
            {"parameter_value_id": 1, "metadata_id": 1, "alternative_id": 1}
        )
        self.assertEqual(len(items), 0)
        self.assertEqual(len(errors), 1)

    def test_add_ext_parameter_value_metadata(self):
        import_functions.import_object_classes(self._db_map, ("fish",))
        import_functions.import_objects(self._db_map, (("fish", "leviathan"),))
        import_functions.import_object_parameters(self._db_map, (("fish", "paranormality"),))
        import_functions.import_object_parameter_values(self._db_map, (("fish", "leviathan", "paranormality", 3.9),))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_ext_parameter_value_metadata(
            {
                "parameter_value_id": 1,
                "metadata_name": "key",
                "metadata_value": "parameter metadata",
                "alternative_id": 1,
            },
            strict=False,
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add value metadata")
        value_metadata = self._db_map.query(self._db_map.ext_parameter_value_metadata_sq).all()
        self.assertEqual(len(value_metadata), 1)
        self.assertEqual(
            dict(value_metadata[0]),
            {
                "alternative_name": "Base",
                "entity_name": "leviathan",
                "parameter_value_id": 1,
                "parameter_name": "paranormality",
                "metadata_name": "key",
                "metadata_value": "parameter metadata",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )

    def test_add_ext_parameter_value_metadata_reuses_existing_metadata(self):
        import_functions.import_object_classes(self._db_map, ("fish",))
        import_functions.import_objects(self._db_map, (("fish", "leviathan"),))
        import_functions.import_object_parameters(self._db_map, (("fish", "paranormality"),))
        import_functions.import_object_parameter_values(self._db_map, (("fish", "leviathan", "paranormality", 3.9),))
        import_functions.import_metadata(self._db_map, ('{"title": "My metadata."}',))
        self._db_map.commit_session("Add test data.")
        items, errors = self._db_map.add_ext_parameter_value_metadata(
            {"parameter_value_id": 1, "metadata_name": "title", "metadata_value": "My metadata.", "alternative_id": 1},
            strict=False,
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)
        self._db_map.commit_session("Add value metadata")
        metadata = self._db_map.query(self._db_map.metadata_sq).all()
        self.assertEqual(len(metadata), 1)
        self.assertEqual(dict(metadata[0]), {"id": 1, "name": "title", "value": "My metadata.", "commit_id": None})
        value_metadata = self._db_map.query(self._db_map.ext_parameter_value_metadata_sq).all()
        self.assertEqual(len(value_metadata), 1)
        self.assertEqual(
            dict(value_metadata[0]),
            {
                "alternative_name": "Base",
                "entity_name": "leviathan",
                "parameter_value_id": 1,
                "parameter_name": "paranormality",
                "metadata_name": "title",
                "metadata_value": "My metadata.",
                "metadata_id": 1,
                "id": 1,
                "commit_id": None,
            },
        )


class TestDatabaseMappingUpdate(unittest.TestCase):
    def setUp(self):
        self._db_map = create_diff_db_map()

    def tearDown(self):
        self._db_map.connection.close()

    def test_update_object_classes(self):
        """Test that updating object classes works."""
        self._db_map.add_object_classes({"id": 1, "name": "fish"}, {"id": 2, "name": "dog"})
        items, intgr_error_log = self._db_map.update_object_classes(
            {"id": 1, "name": "octopus"}, {"id": 2, "name": "god"}
        )
        ids = {x["id"] for x in items}
        self._db_map.commit_session("test commit")
        sq = self._db_map.object_class_sq
        object_classes = {x.id: x.name for x in self._db_map.query(sq).filter(sq.c.id.in_(ids))}
        self.assertEqual(intgr_error_log, [])
        self.assertEqual(object_classes[1], "octopus")
        self.assertEqual(object_classes[2], "god")

    def test_update_objects(self):
        """Test that updating objects works."""
        self._db_map.add_object_classes({"id": 1, "name": "fish"})
        self._db_map.add_objects({"id": 1, "name": "nemo", "class_id": 1}, {"id": 2, "name": "dory", "class_id": 1})
        items, intgr_error_log = self._db_map.update_objects({"id": 1, "name": "klaus"}, {"id": 2, "name": "squidward"})
        ids = {x["id"] for x in items}
        self._db_map.commit_session("test commit")
        sq = self._db_map.object_sq
        objects = {x.id: x.name for x in self._db_map.query(sq).filter(sq.c.id.in_(ids))}
        self.assertEqual(intgr_error_log, [])
        self.assertEqual(objects[1], "klaus")
        self.assertEqual(objects[2], "squidward")

    def test_update_objects_not_committed(self):
        """Test that updating objects works."""
        self._db_map.add_object_classes({"id": 1, "name": "some_class"})
        self._db_map.add_objects({"id": 1, "name": "nemo", "class_id": 1})
        items, intgr_error_log = self._db_map.update_objects({"id": 1, "name": "klaus"})
        ids = {x["id"] for x in items}
        self._db_map.commit_session("test commit")
        sq = self._db_map.object_sq
        objects = {x.id: x.name for x in self._db_map.query(sq).filter(sq.c.id.in_(ids))}
        self.assertEqual(intgr_error_log, [])
        self.assertEqual(objects[1], "klaus")
        self.assertEqual(self._db_map.query(self._db_map.object_sq).filter_by(id=1).first().name, "klaus")

    def test_update_committed_object(self):
        """Test that updating objects works."""
        self._db_map.add_object_classes({"id": 1, "name": "some_class"})
        self._db_map.add_objects({"id": 1, "name": "nemo", "class_id": 1})
        self._db_map.commit_session("update")
        items, intgr_error_log = self._db_map.update_objects({"id": 1, "name": "klaus"})
        ids = {x["id"] for x in items}
        self._db_map.commit_session("test commit")
        sq = self._db_map.object_sq
        objects = {x.id: x.name for x in self._db_map.query(sq).filter(sq.c.id.in_(ids))}
        self.assertEqual(intgr_error_log, [])
        self.assertEqual(objects[1], "klaus")
        self.assertEqual(self._db_map.query(self._db_map.object_sq).filter_by(id=1).first().name, "klaus")

    def test_update_relationship_classes(self):
        """Test that updating relationship classes works."""
        self._db_map.add_object_classes({"name": "dog", "id": 1}, {"name": "fish", "id": 2})
        self._db_map.add_wide_relationship_classes(
            {"id": 3, "name": "dog__fish", "object_class_id_list": [1, 2]},
            {"id": 4, "name": "fish__dog", "object_class_id_list": [2, 1]},
        )
        items, intgr_error_log = self._db_map.update_wide_relationship_classes(
            {"id": 3, "name": "god__octopus"}, {"id": 4, "name": "octopus__dog"}
        )
        ids = {x["id"] for x in items}
        self._db_map.commit_session("test commit")
        sq = self._db_map.wide_relationship_class_sq
        rel_clss = {x.id: x.name for x in self._db_map.query(sq).filter(sq.c.id.in_(ids))}
        self.assertEqual(intgr_error_log, [])
        self.assertEqual(rel_clss[3], "god__octopus")
        self.assertEqual(rel_clss[4], "octopus__dog")

    def test_update_relationships(self):
        """Test that updating relationships works."""
        self._db_map.add_object_classes({"name": "fish", "id": 1}, {"name": "dog", "id": 2})
        self._db_map.add_wide_relationship_classes({"name": "fish__dog", "id": 3, "object_class_id_list": [1, 2]})
        self._db_map.add_objects(
            {"name": "nemo", "id": 1, "class_id": 1},
            {"name": "pluto", "id": 2, "class_id": 2},
            {"name": "scooby", "id": 3, "class_id": 2},
        )
        self._db_map.add_wide_relationships(
            {"id": 4, "name": "nemo__pluto", "class_id": 3, "object_id_list": [1, 2], "object_class_id_list": [1, 2]}
        )
        items, intgr_error_log = self._db_map.update_wide_relationships(
            {"id": 4, "name": "nemo__scooby", "class_id": 3, "object_id_list": [1, 3], "object_class_id_list": [1, 2]}
        )
        ids = {x["id"] for x in items}
        self._db_map.commit_session("test commit")
        sq = self._db_map.wide_relationship_sq
        rels = {
            x.id: {"name": x.name, "object_id_list": x.object_id_list}
            for x in self._db_map.query(sq).filter(sq.c.id.in_(ids))
        }
        self.assertEqual(intgr_error_log, [])
        self.assertEqual(rels[4]["name"], "nemo__scooby")
        self.assertEqual(rels[4]["object_id_list"], "1,3")


class TestDatabaseMappingCommit(unittest.TestCase):
    def setUp(self):
        self._db_map = create_diff_db_map()

    def tearDown(self):
        self._db_map.connection.close()

    def test_commit_message(self):
        """Tests that commit comment ends up in the database."""
        self._db_map.add_object_classes({"name": "testclass"})
        self._db_map.commit_session("test commit")
        self.assertEqual(self._db_map.query(self._db_map.commit_sq).all()[-1].comment, "test commit")
        self._db_map.connection.close()

    def test_commit_session_raise_with_empty_comment(self):
        import_functions.import_object_classes(self._db_map, ("my_class",))
        self.assertRaisesRegex(SpineDBAPIError, "Commit message cannot be empty.", self._db_map.commit_session, "")

    def test_commit_session_raise_when_nothing_to_commit(self):
        self.assertRaisesRegex(SpineDBAPIError, "Nothing to commit.", self._db_map.commit_session, "No changes.")


if __name__ == "__main__":
    unittest.main()
