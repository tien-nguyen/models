import pytest
import torch

import merlin.models.torch as mm
from merlin.models.torch.inputs.embedding import infer_embedding_dim
from merlin.models.torch.utils import module_utils
from merlin.schema import ColumnSchema, Schema, Tags


class TestTabularInputBlock:
    @pytest.fixture(autouse=True)
    def setup_method(self, music_streaming_data):
        self.schema: Schema = music_streaming_data.schema
        self.input_block: mm.TabularInputBlock = mm.TabularInputBlock(self.schema)
        self.batch: mm.Batch = mm.Batch.sample_from(music_streaming_data, batch_size=10)

    def test_forward(self):
        self.input_block.add_route(Tags.CONTINUOUS)
        self.input_block.add_route(Tags.CATEGORICAL, mm.EmbeddingTable(10, seq_combiner="mean"))

        outputs = module_utils.module_test(self.input_block, self.batch)

        for name in mm.schema.select(self.schema, Tags.CONTINUOUS).column_names:
            assert name in outputs

        for name in mm.schema.select(self.schema, Tags.CATEGORICAL).column_names:
            assert name in outputs
            assert outputs[name].shape == (10, 10)

    def test_init_detaults(self):
        input_block = mm.TabularInputBlock(self.schema, init="defaults")
        outputs = module_utils.module_test(input_block, self.batch)

        for name in mm.schema.select(self.schema, Tags.CONTINUOUS).column_names:
            assert name in outputs

        for name in mm.schema.select(self.schema, Tags.CATEGORICAL).column_names:
            assert name in outputs
            assert outputs[name].shape == (
                10,
                infer_embedding_dim(self.schema.select_by_name(name)),
            )

    def test_init_agg(self):
        input_block = mm.TabularInputBlock(self.schema, init="defaults", agg="concat")
        outputs = module_utils.module_test(input_block, self.batch)

        assert isinstance(outputs, torch.Tensor)
        assert outputs.shape == (10, 107)

    def test_exceptions(self):
        with pytest.raises(ValueError):
            mm.TabularInputBlock(self.schema, init="unknown")

    def test_extract_route_two_tower(self):
        input_block = mm.TabularInputBlock(self.schema, init="defaults")
        towers = input_block.reroute()
        towers.add_route(Tags.USER, mm.MLPBlock([10]))
        towers.add_route(Tags.ITEM, mm.MLPBlock([10]))

        input_cols = {
            "user_id",
            "country",
            "user_age",
            "user_genres",
            "item_id",
            "item_category",
            "item_recency",
            "item_genres",
        }
        assert set(mm.schema.input(towers).column_names) == input_cols
        assert mm.schema.output(towers).column_names == ["user", "item"]

        categorical = towers.select(Tags.CATEGORICAL)
        outputs = module_utils.module_test(towers, self.batch)

        assert mm.schema.extract(towers, Tags.CATEGORICAL)[1] == categorical
        assert set(mm.schema.input(towers).column_names) == input_cols
        assert mm.schema.output(towers).column_names == ["user", "item"]

        outputs = towers(self.batch.features)
        assert outputs["user"].shape == (10, 10)
        assert outputs["item"].shape == (10, 10)

        new_inputs, route = mm.schema.extract(towers, Tags.USER)
        assert mm.schema.output(new_inputs).column_names == ["user", "item"]

        assert "user" in new_inputs.branches
        assert new_inputs.branches["user"][0].select_keys.column_names == ["user"]
        assert "user" in route.branches
        assert mm.schema.output(route).select_by_tag(Tags.EMBEDDING).column_names == ["user"]

    def test_extract_route_embeddings(self):
        input_block = mm.TabularInputBlock(self.schema, init="defaults", agg="concat")

        outputs = module_utils.module_test(input_block, self.batch)
        assert outputs.shape == (10, 107)

        no_embs, emb_route = mm.schema.extract(input_block, Tags.CATEGORICAL)
        output_schema = mm.schema.output(emb_route)

        assert len(output_schema.select_by_tag(Tags.USER)) == 3
        assert len(output_schema.select_by_tag(Tags.ITEM)) == 3
        assert len(output_schema.select_by_tag(Tags.SESSION)) == 1

        assert no_embs

    def test_extract_route_nesting(self):
        input_block = mm.TabularInputBlock(self.schema, init="defaults", agg="concat")

        outputs = module_utils.module_test(input_block, self.batch)
        assert outputs.shape == (10, 107)

        no_user_id, user_id_route = input_block.extract(ColumnSchema("user_id"))

        assert no_user_id

    def test_extract_double_nesting(self):
        input_block = mm.TabularInputBlock(self.schema, agg="concat")
        input_block.add_route(Tags.CONTINUOUS)
        input_block.add_route(
            Tags.CATEGORICAL,
            mm.Block(
                mm.EmbeddingTables(10, seq_combiner="mean"),
            ),
        )

        outputs = module_utils.module_test(input_block, self.batch)
        assert outputs.shape == (10, 73)

        no_user_id, user_id_route = mm.schema.extract(input_block, Tags.USER_ID)

        assert no_user_id
