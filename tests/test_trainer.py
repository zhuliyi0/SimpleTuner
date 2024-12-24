# test_trainer.py

import unittest
from unittest.mock import Mock, patch, MagicMock
import torch, os

os.environ["SIMPLETUNER_LOG_LEVEL"] = "CRITICAL"
from helpers.training.trainer import Trainer


class TestTrainer(unittest.TestCase):
    @patch("helpers.training.trainer.load_config")
    @patch("helpers.training.trainer.safety_check")
    @patch(
        "helpers.training.trainer.load_scheduler_from_args",
        return_value=(Mock(), None, Mock()),
    )
    @patch("helpers.training.state_tracker.StateTracker")
    @patch(
        "helpers.training.state_tracker.StateTracker.set_model_family",
        return_value=True,
    )
    @patch("torch.set_num_threads")
    @patch("helpers.training.trainer.Accelerator")
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    def test_config_to_obj(
        self,
        mock_misc_init,
        mock_parse_args,
        mock_accelerator,
        mock_set_num_threads,
        mock_set_model_family,
        mock_state_tracker,
        mock_load_scheduler_from_args,
        mock_safety_check,
        mock_load_config,
    ):
        trainer = Trainer()
        config_dict = {"a": 1, "b": 2}
        config_obj = trainer._config_to_obj(config_dict)
        self.assertEqual(config_obj.a, 1)
        self.assertEqual(config_obj.b, 2)

        config_none = trainer._config_to_obj(None)
        self.assertIsNone(config_none)

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.set_seed")
    def test_init_seed_with_value(self, mock_set_seed, mock_parse_args, mock_misc_init):
        trainer = Trainer()
        trainer.config = Mock(seed=42, seed_for_each_device=False)
        trainer.init_seed()
        mock_set_seed.assert_called_with(42, False)

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.set_seed")
    def test_init_seed_none(self, mock_set_seed, mock_parse_args, mock_misc_init):
        trainer = Trainer()
        trainer.config = Mock(seed=None, seed_for_each_device=False)
        trainer.init_seed()
        mock_set_seed.assert_not_called()

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.memory_allocated", return_value=1024**3)
    def test_stats_memory_used_cuda(
        self, mock_memory_allocated, mock_is_available, mock_parse_args, mock_misc_init
    ):
        trainer = Trainer()
        memory_used = trainer.stats_memory_used()
        self.assertEqual(memory_used, 1.0)

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("torch.cuda.is_available", return_value=False)
    @patch("torch.backends.mps.is_available", return_value=True)
    @patch("torch.mps.current_allocated_memory", return_value=1024**3)
    def test_stats_memory_used_mps(
        self,
        mock_current_allocated_memory,
        mock_mps_is_available,
        mock_cuda_is_available,
        mock_parse_args,
        mock_misc_init,
    ):
        trainer = Trainer()
        memory_used = trainer.stats_memory_used()
        self.assertEqual(memory_used, 1.0)

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("torch.cuda.is_available", return_value=False)
    @patch("torch.backends.mps.is_available", return_value=False)
    @patch("helpers.training.trainer.logger")
    def test_stats_memory_used_none(
        self,
        mock_logger,
        mock_mps_is_available,
        mock_cuda_is_available,
        mock_parse_args,
        mock_misc_init,
    ):
        trainer = Trainer()
        memory_used = trainer.stats_memory_used()
        self.assertEqual(memory_used, 0)
        mock_logger.warning.assert_called_with(
            "CUDA, ROCm, or Apple MPS not detected here. We cannot report VRAM reductions."
        )

    @patch("torch.set_num_threads")
    @patch("helpers.training.state_tracker.StateTracker.set_global_step")
    @patch("helpers.training.state_tracker.StateTracker.set_args")
    @patch("helpers.training.state_tracker.StateTracker.set_weight_dtype")
    @patch("helpers.training.trainer.Trainer.set_model_family")
    @patch("helpers.training.trainer.Trainer.init_noise_schedule")
    @patch(
        "accelerate.accelerator.Accelerator",
        return_value=Mock(device=Mock(type="cuda")),
    )
    @patch("accelerate.state.AcceleratorState", Mock())
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=MagicMock(
            torch_num_threads=2,
            train_batch_size=1,
            weight_dtype=torch.float32,
            optimizer="adamw_bf16",
            max_train_steps=2,
            num_train_epochs=0,
            timestep_bias_portion=0,
            metadata_update_interval=100,
            gradient_accumulation_steps=1,
            mixed_precision="bf16",
            report_to="none",
            output_dir="output_dir",
            flux_schedule_shift=3,
            flux_schedule_auto_shift=False,
            validation_guidance_skip_layers=None,
            gradient_checkpointing_interval=None,
        ),
    )
    def test_misc_init(
        self,
        mock_argparse,
        # mock_accelerator_state,
        mock_accelerator,
        mock_init_noise_schedule,
        mock_set_model_family,
        mock_set_weight_dtype,
        mock_set_args,
        mock_set_global_step,
        mock_set_num_threads,
    ):
        trainer = Trainer(disable_accelerator=True)
        trainer._misc_init()
        mock_set_num_threads.assert_called_with(2)
        self.assertEqual(
            trainer.state,
            {"lr": 0.0, "global_step": 0, "global_resume_step": 0, "first_epoch": 1},
        )
        self.assertEqual(trainer.timesteps_buffer, [])
        self.assertEqual(trainer.guidance_values_list, [])
        self.assertEqual(trainer.train_loss, 0.0)
        self.assertIsNone(trainer.bf)
        self.assertIsNone(trainer.grad_norm)
        self.assertEqual(trainer.extra_lr_scheduler_kwargs, {})
        mock_set_global_step.assert_called_with(0)
        mock_set_args.assert_called_with(trainer.config)
        mock_set_weight_dtype.assert_called_with(trainer.config.weight_dtype)
        mock_set_model_family.assert_called()
        mock_init_noise_schedule.assert_called()

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch(
        "helpers.training.trainer.load_scheduler_from_args",
        return_value=(Mock(), "flow_matching_value", "noise_scheduler_value"),
    )
    def test_init_noise_schedule(
        self, mock_load_scheduler_from_args, mock_parse_args, mock_misc_init
    ):
        trainer = Trainer()
        trainer.config = Mock()
        trainer.init_noise_schedule()
        self.assertEqual(trainer.config.flow_matching, "flow_matching_value")
        self.assertEqual(trainer.noise_scheduler, "noise_scheduler_value")
        self.assertEqual(trainer.lr, 0.0)

    @patch("helpers.training.trainer.logger")
    @patch(
        "helpers.training.trainer.model_classes", {"full": ["sdxl", "sd3", "legacy"]}
    )
    @patch(
        "helpers.training.trainer.model_labels",
        {"sdxl": "SDXL", "sd3": "SD3", "legacy": "Legacy"},
    )
    @patch("helpers.training.state_tracker.StateTracker")
    def test_set_model_family_default(self, mock_state_tracker, mock_logger):
        with patch("helpers.training.trainer.Trainer._misc_init"):
            with patch("helpers.training.trainer.Trainer.parse_arguments"):
                trainer = Trainer()
        trainer.config = Mock(model_family=None)
        trainer.config.pretrained_model_name_or_path = "some/path"
        trainer.config.pretrained_vae_model_name_or_path = None
        trainer.config.vae_path = None
        trainer.config.text_encoder_path = None
        trainer.config.text_encoder_subfolder = None
        trainer.config.model_family = None

        with patch.object(trainer, "_set_model_paths") as mock_set_model_paths:
            with patch(
                "helpers.training.state_tracker.StateTracker.is_sdxl_refiner",
                return_value=False,
            ):
                trainer.set_model_family()
                self.assertEqual(trainer.config.model_type_label, "SDXL")
                mock_logger.warning.assert_called()
                mock_set_model_paths.assert_called()

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    def test_set_model_family_invalid(self, mock_parse_args, mock_misc_init):
        trainer = Trainer()
        trainer.config = Mock(model_family="invalid_model_family")
        trainer.config.pretrained_model_name_or_path = "some/path"
        with self.assertRaises(ValueError) as context:
            trainer.set_model_family()
        self.assertIn(
            "Invalid model family specified: invalid_model_family",
            str(context.exception),
        )

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.logger")
    @patch("helpers.training.state_tracker.StateTracker")
    def test_epoch_rollover(
        self, mock_state_tracker, mock_logger, mock_parse_args, mock_misc_init
    ):
        trainer = Trainer()
        trainer.state = {"first_epoch": 1, "current_epoch": 1}
        trainer.config = Mock(
            num_train_epochs=5,
            aspect_bucket_disable_rebuild=False,
            lr_scheduler="cosine_with_restarts",
        )
        trainer.extra_lr_scheduler_kwargs = {}
        with patch(
            "helpers.training.state_tracker.StateTracker.get_data_backends",
            return_value={},
        ):
            trainer._epoch_rollover(2)
            self.assertEqual(trainer.state["current_epoch"], 2)
            self.assertEqual(trainer.extra_lr_scheduler_kwargs["epoch"], 2)

    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    def test_epoch_rollover_same_epoch(self, mock_misc_init, mock_parse_args):
        trainer = Trainer(
            config={
                "--num_train_epochs": 0,
                "--model_family": "pixart_sigma",
                "--optimizer": "adamw_bf16",
                "--pretrained_model_name_or_path": "some/path",
            }
        )
        trainer.state = {"first_epoch": 1, "current_epoch": 1}
        trainer._epoch_rollover(1)
        self.assertEqual(trainer.state["current_epoch"], 1)

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.os.makedirs")
    @patch("helpers.training.state_tracker.StateTracker.delete_cache_files")
    def test_init_clear_backend_cache_preserve(
        self, mock_delete_cache_files, mock_makedirs, mock_parse_args, mock_misc_init
    ):
        trainer = Trainer()
        trainer.config = Mock(
            output_dir="/path/to/output", preserve_data_backend_cache=True
        )
        trainer.init_clear_backend_cache()
        mock_makedirs.assert_called_with("/path/to/output", exist_ok=True)
        mock_delete_cache_files.assert_not_called()

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.os.makedirs")
    @patch("helpers.training.state_tracker.StateTracker.delete_cache_files")
    def test_init_clear_backend_cache_delete(
        self, mock_delete_cache_files, mock_makedirs, mock_parse_args, mock_misc_init
    ):
        trainer = Trainer()
        trainer.config = Mock(
            output_dir="/path/to/output", preserve_data_backend_cache=False
        )
        trainer.init_clear_backend_cache()
        mock_makedirs.assert_called_with("/path/to/output", exist_ok=True)
        mock_delete_cache_files.assert_called_with(preserve_data_backend_cache=False)

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.huggingface_hub")
    @patch("helpers.training.trainer.HubManager")
    @patch("helpers.training.state_tracker.StateTracker")
    @patch("accelerate.logging.MultiProcessAdapter.log")
    def test_init_huggingface_hub(
        self,
        mock_logger,
        mock_state_tracker,
        mock_hub_manager_class,
        mock_hf_hub,
        mock_parse_args,
        mock_misc_init,
    ):
        trainer = Trainer()
        trainer.config = Mock(push_to_hub=True, huggingface_token="fake_token")
        trainer.accelerator = Mock(is_main_process=True)
        mock_hf_hub.whoami = Mock(return_value={"id": "fake_id", "name": "foobar"})
        trainer.init_huggingface_hub(access_token="fake_token")
        mock_hf_hub.login.assert_called_with(token="fake_token")
        mock_hub_manager_class.assert_called_with(config=trainer.config)
        mock_hf_hub.whoami.assert_called()

    @patch("helpers.training.trainer.Trainer._misc_init", return_value=Mock())
    @patch("helpers.training.trainer.Trainer.parse_arguments", return_value=Mock())
    @patch("helpers.training.trainer.logger")
    @patch("helpers.training.trainer.os.path.basename", return_value="checkpoint-100")
    @patch(
        "helpers.training.trainer.os.listdir",
        return_value=["checkpoint-100", "checkpoint-200"],
    )
    @patch(
        "helpers.training.trainer.os.path.join",
        side_effect=lambda *args: "/".join(args),
    )
    @patch("helpers.training.trainer.os.path.exists", return_value=True)
    @patch("helpers.training.trainer.Accelerator")
    @patch("helpers.training.state_tracker.StateTracker")
    def test_init_resume_checkpoint(
        self,
        mock_state_tracker,
        mock_accelerator_class,
        mock_path_exists,
        mock_path_join,
        mock_os_listdir,
        mock_path_basename,
        mock_logger,
        mock_parse_args,
        mock_misc_init,
    ):
        trainer = Trainer()
        trainer.config = Mock(
            output_dir="/path/to/output",
            resume_from_checkpoint="latest",
            total_steps_remaining_at_start=100,
            global_resume_step=1,
            num_train_epochs=0,
            max_train_steps=100,
        )
        trainer.accelerator = Mock(num_processes=1)
        trainer.state = {"global_step": 0, "first_epoch": 1, "current_epoch": 1}
        trainer.optimizer = Mock()
        trainer.config.lr_scheduler = "constant"
        trainer.config.learning_rate = 0.001
        trainer.config.is_schedulefree = False
        trainer.config.overrode_max_train_steps = False

        # Mock lr_scheduler
        lr_scheduler = Mock()
        lr_scheduler.state_dict.return_value = {"base_lrs": [0.1], "_last_lr": [0.1]}

        with patch(
            "helpers.training.state_tracker.StateTracker.get_data_backends",
            return_value={},
        ):
            with patch(
                "helpers.training.state_tracker.StateTracker.get_global_step",
                return_value=100,
            ):
                trainer.init_resume_checkpoint(lr_scheduler=lr_scheduler)
                mock_logger.info.assert_called()
                trainer.accelerator.load_state.assert_called_with(
                    "/path/to/output/checkpoint-200"
                )

    # Additional tests can be added for other methods as needed


if __name__ == "__main__":
    unittest.main()
