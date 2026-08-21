from pathlib import Path


MAIN_WINDOW_SOURCE = Path("app/ui/main_window.py").read_text(encoding="utf-8")


def test_image2vid_long_prompts_are_inside_resizable_scroll_area() -> None:
    assert "self.image2vid_long_prompts_scroll = QScrollArea()" in MAIN_WINDOW_SOURCE
    assert "self.image2vid_long_prompts_scroll.setWidgetResizable(True)" in MAIN_WINDOW_SOURCE
    assert (
        "self.image2vid_long_prompts_scroll.setWidget(self.image2vid_long_prompts_group)"
        in MAIN_WINDOW_SOURCE
    )
    assert "long_layout.addWidget(self.image2vid_long_prompts_scroll, 1)" in MAIN_WINDOW_SOURCE


def test_image2vid_long_generate_button_remains_outside_prompt_scroll_area() -> None:
    scroll_index = MAIN_WINDOW_SOURCE.index(
        "self.image2vid_long_prompts_scroll.setWidget(self.image2vid_long_prompts_group)"
    )
    button_index = MAIN_WINDOW_SOURCE.index(
        'self.image2vid_long_generate_btn = QPushButton("Crear proyecto Image2Vid Long")'
    )
    button_layout_index = MAIN_WINDOW_SOURCE.index(
        "long_layout.addWidget(self.image2vid_long_generate_btn)"
    )

    assert scroll_index < button_index < button_layout_index


def test_image2vid_long_can_switch_between_fixed_and_per_prompt_random_seed() -> None:
    assert "self.image2vid_long_seed_spin = QSpinBox()" in MAIN_WINDOW_SOURCE
    assert "self.image2vid_long_seed_spin.setRange(0, 2**31 - 1)" in MAIN_WINDOW_SOURCE
    assert 'self.image2vid_long_random_seed_btn = QPushButton("Seed aleatorio")' in MAIN_WINDOW_SOURCE
    assert (
        'self.image2vid_long_fixed_seed_check = QCheckBox("Seed fija en todos los prompts")'
        in MAIN_WINDOW_SOURCE
    )
    assert "self.image2vid_long_fixed_seed_check.setChecked(True)" in MAIN_WINDOW_SOURCE
    assert "fixed_seed=fixed_seed" in MAIN_WINDOW_SOURCE
