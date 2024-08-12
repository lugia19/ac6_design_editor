import math
import os
import sys
import zlib, struct
from typing import List

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QFrame, QGridLayout, QComboBox, QCompleter, QColorDialog, QCheckBox, \
    QStackedWidget, QSpacerItem, QSizePolicy, QMessageBox, QScrollArea
from PyQt6.QtCore import Qt, QSize, QRect
from PyQt6.QtGui import QPainter, QPainterPath, QColor
from PyQt6.QtWidgets import QAbstractButton, QSizePolicy
from io import BytesIO

# Define the category offsets
CATEGORY_OFFSETS = {
    'weapon': 0x00000000,
    'body_part': 0x10000000,  # Head, Body, Arms, Legs
    'generator': 0x50000000,
    'booster': 0x60000000,
    'fcs': 0x70000000
}

color_section_labels = ["Head", "Core", "R arm", "L arm", "Legs", "R wep", "L wep", "R back", "L back"]
color_labels = ["Main", "Sub", "Support", "Optional", "Other", "Device"]
materials_list = []
for i in range(36):
    materials_list.append(f"{i} - Reflectiveness: {round(math.floor(i/6)*0.2, 2)} Luster: {round((i % 6) * 0.2,2)}")


pattern_list = ["Pattern 0 (None)"]
for i in range(29):
    pattern_list.append(f"Pattern {i+1}")
pattern_size_list = ['0 - Small', '1 - Medium', '2 - Large']
weathering_list = ['Weathered 0 (None)']
for i in range(23):
    weathering_list.append(f"Weathered {i}")

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class CustomCheckBox(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRect(rect)

        if self.isChecked():
            painter.fillPath(path, QColor(colors_dict["secondary_color"]))  # Fill color when checked
        else:
            painter.fillPath(path, QColor(colors_dict["secondary_color"]))  # Fill color when unchecked

        painter.setPen(QColor(colors_dict["text_color"]))  # Border color
        painter.drawPath(path)

        if self.isChecked():
            check_path = QPainterPath()
            check_path.moveTo(rect.left() + 4, rect.center().y())
            check_path.lineTo(rect.center().x() - 2, rect.bottom() - 4)
            check_path.lineTo(rect.right() - 4, rect.top() + 4)
            painter.setPen(QColor(colors_dict["text_color"]))  # Check mark color
            painter.drawPath(check_path)

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

    def sizeHint(self):
        return QSize(20, 20)  # Adjust the size as needed

class ChunkHeader:
    def __init__(self, signature, length, version):
        self.signature = signature
        self.length = length
        self.version = version

    def __str__(self):
        return f"{self.signature:<15} v{self.version} [{self.length:5X}h]"

    @classmethod
    def from_bytes(cls, data):
        signature = data[:0x10].rstrip(b'\x00').decode('ascii')
        length, version, unk18, unk1c = struct.unpack('<IIII', data[0x10:0x20])
        assert unk18 == 0 and unk1c == 0, "Unexpected values in chunk header"
        return cls(signature, length, version)

    def to_bytes(self):
        signature_bytes = self.signature.encode('ascii').ljust(0x10, b'\x00')
        header_bytes = struct.pack('<IIII', self.length, self.version, 0, 0)
        return signature_bytes + header_bytes

class ColorRowData:
    def __init__(self, color_name, color=None, material=None, pattern=False):
        self.color_name = color_name
        self.color = color or QColor(255, 255, 255)  # Default to white if no color is provided
        self.material = material
        self.pattern = pattern

class ColoringSectionData:
    def __init__(self, name):
        self.name = name
        self.color_rows = []
        self.pattern_number = None
        self.pattern_size = None
        self.pattern_colors = []
        self.weathering = None

    def to_bytes(self):
        data = bytearray()
        data.extend(b'\xff\x00\x00\x00')  # unk00
        data.extend(struct.pack('<h', int(self.weathering.split(" ")[1]) or 0))  # weathering
        data.extend(b'\x00\x00')  # unk06

        for color_row in self.color_rows:
            color = color_row.color
            data.extend(struct.pack('<BBBB', color.red(), color.green(), color.blue(), color.alpha()))

        for color_row in self.color_rows:
            material = color_row.material
            material_index = 0  # Default to 0 if material is not found
            if material:
                material_index = int(material.split(' - ')[0])  # Extract the material index from the string
            data.extend(struct.pack('<h', material_index))

        data.extend(struct.pack('<B', int(self.pattern_number.split(" ")[1]) or 0))  # patternDesign
        data.extend(struct.pack('<B', int(self.pattern_size.split(" - ")[0]) or 0))  # patternSize
        data.extend(b'\x00\x00')  # unk2e

        for color in self.pattern_colors:
            data.extend(struct.pack('<BBBB', color.red(), color.green(), color.blue(), color.alpha()))

        # Calculate unk40 based on the pattern checkbox states
        unk40 = 0b00111111  # Default value with all bits set to 1
        for i, color_row in enumerate(reversed(self.color_rows[:5])):
            if color_row.pattern:
                unk40 &= ~(1 << (i + 2))  # Set the corresponding bit to 0 if pattern is enabled

        data.extend(struct.pack('<H', unk40))  # unk40
        data.extend(b'\x00\x00')  # unk42

        return bytes(data)

    @classmethod
    def from_bytes(cls, name, data):
        coloring_section = cls(name)

        # Skip unk00
        weathering = struct.unpack('<h', data[4:6])[0]
        coloring_section.weathering = weathering

        # Skip unk06

        for i in range(6):
            start = 8 + i * 4
            end = start + 4
            rgba = struct.unpack('<BBBB', data[start:end])
            color = QColor(*rgba)
            coloring_section.color_rows.append(ColorRowData(color_labels[i], color=color))

        for i in range(6):
            start = 32 + i * 2
            end = start + 2
            material_index = struct.unpack('<h', data[start:end])[0]
            material = f"{material_index}"  # Placeholder material string
            coloring_section.color_rows[i].material = material

        coloring_section.pattern_number = data[44]
        coloring_section.pattern_size = data[45]

        # Skip unk2e

        for i in range(4):
            start = 48 + i * 4
            end = start + 4
            rgba = struct.unpack('<BBBB', data[start:end])
            color = QColor(*rgba)
            coloring_section.pattern_colors.append(color)
        if len(data) < 66:
            data += b"\x00\x00"
        unk40 = struct.unpack('<H', data[64:66])[0]
        for i, color_row in enumerate(reversed(coloring_section.color_rows[:5])):
            color_row.pattern = not bool(unk40 & (1 << (i + 2)))

        # Skip unk42

        return coloring_section


class ColorRow(QWidget):
    def __init__(self, color_label, parent=None):
        super().__init__(parent)
        self.color_name = color_label
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(self.color_name)
        layout.addWidget(self.label)

        self.color_picker = QPushButton()
        self.color_picker.clicked.connect(self.open_color_picker)
        layout.addWidget(self.color_picker)

        self.material_dropdown = QComboBox()
        self.material_dropdown.addItems(materials_list)  # Dummy options
        layout.addWidget(self.material_dropdown)

        checkbox_container = QHBoxLayout()
        self.pattern_checkbox = CustomCheckBox()
        checkbox_container.addWidget(self.pattern_checkbox)
        self.pattern_checkbox_padder = QLabel("")
        checkbox_container.addWidget(self.pattern_checkbox_padder)
        #checkbox_container.addStretch(1)
        layout.addLayout(checkbox_container)
        self.row_layout = layout
        self.setLayout(layout)

    def open_color_picker(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color_picker.setStyleSheet(f'background-color: {color.name()};')

    def set_row_type(self, row_type):
        if row_type == "full":
            self.material_dropdown.setVisible(True)
            self.pattern_checkbox.setVisible(True)
            self.pattern_checkbox_padder.setVisible(True)
        elif row_type == "color_only":
            self.material_dropdown.setVisible(False)
            self.pattern_checkbox.setVisible(False)
            self.pattern_checkbox_padder.setVisible(False)

    def import_settings(self, settings):
        self.color_picker.setStyleSheet(f'background-color: {settings.color.name()};')
        if settings.material:
            if settings.material.isnumeric():
                index = self.material_dropdown.findText(f"{settings.material} - ", flags=Qt.MatchFlag.MatchContains)
            else:
                index = self.material_dropdown.findText(settings.material, flags=Qt.MatchFlag.MatchContains)
            if index >= 0:
                self.material_dropdown.setCurrentIndex(index)
        self.pattern_checkbox.setChecked(settings.pattern)

    def export_settings(self):
        return ColorRowData(
            self.label.text(),
            QColor(self.color_picker.palette().button().color()),
            self.material_dropdown.currentText(),
            self.pattern_checkbox.isChecked()
        )

class ColoringSection(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Add a label with the section name
        self.name_label = QLabel(self.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-weight: bold;")
        new_font = self.name_label.font()
        new_font.setPointSize(12)
        self.name_label.setFont(new_font)
        layout.addWidget(self.name_label)

        coloring_line = QFrame()
        coloring_line.setFrameShape(QFrame.Shape.HLine)
        coloring_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(coloring_line)

        coloring_layout = QVBoxLayout()

        # Column labels
        labels_layout = QHBoxLayout()
        labels_layout.addWidget(QLabel('Color name'))
        labels_layout.addWidget(QLabel('Color picker'))
        labels_layout.addWidget(QLabel('Material'))
        labels_layout.addWidget(QLabel('Print Pattern'))
        coloring_layout.addLayout(labels_layout)

        self.color_rows = []

        # Six rows of color pickers
        for i, color_label in enumerate(color_labels):
            color_row = ColorRow(color_label)
            if i == len(color_labels) - 1:  # Last row
                color_row.set_row_type("color_only")
                color_row.row_layout.addWidget(QLabel(""))
                color_row.row_layout.addWidget(QLabel(""))
                #color_row.row_layout.addStretch()
            else:
                color_row.set_row_type("full")
            coloring_layout.addWidget(color_row)
            self.color_rows.append(color_row)

        # Pattern and Pattern Size dropdowns
        hbox_wrap = QHBoxLayout()
        pattern_label = QLabel("Pattern")
        pattern_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        hbox_wrap.addStretch()
        hbox_wrap.addWidget(pattern_label)
        hbox_wrap.addStretch()
        coloring_layout.addLayout(hbox_wrap)


        pattern_layout = QHBoxLayout()
        pattern_layout.addWidget(QLabel('Pattern number'))
        self.pattern_dropdown = QComboBox()
        self.pattern_dropdown.addItems(pattern_list)  # Dummy options
        pattern_layout.addWidget(self.pattern_dropdown)
        pattern_layout.addWidget(QLabel('Pattern Size'))
        self.pattern_size_dropdown = QComboBox()
        self.pattern_size_dropdown.addItems(pattern_size_list)  # Dummy options
        pattern_layout.addWidget(self.pattern_size_dropdown)
        coloring_layout.addLayout(pattern_layout)

        # Two rows with two color pickers each
        self.pattern_color_rows = []
        for i in range(2):
            color_pickers_layout = QHBoxLayout()
            for j in range(2):
                color_row = ColorRow(f"Color {(i + 1) + (j + 1)}")
                color_row.set_row_type("color_only")
                color_pickers_layout.addWidget(color_row)
                self.pattern_color_rows.append(color_row)
            coloring_layout.addLayout(color_pickers_layout)

        # Weathering dropdown
        weathering_layout = QHBoxLayout()
        weathering_layout.addWidget(QLabel('Weathering:'))
        self.weathering_dropdown = QComboBox()
        self.weathering_dropdown.addItems(weathering_list)  # Dummy options
        weathering_layout.addWidget(self.weathering_dropdown)
        weathering_layout.addWidget(QLabel(""))
        weathering_layout.addWidget(QLabel(""))
        coloring_layout.addLayout(weathering_layout)

        layout.addLayout(coloring_layout)

        self.setLayout(layout)

    def open_color_picker(self, button):
        color = QColorDialog.getColor()
        if color.isValid():
            button.setStyleSheet(f'background-color: {color.name()};')

    def import_settings(self, settings):
        for i, color_row_settings in enumerate(settings.color_rows):
            if i < len(self.color_rows):
                self.color_rows[i].import_settings(color_row_settings)

        index = self.pattern_dropdown.findText(str(settings.pattern_number), flags=Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.pattern_dropdown.setCurrentIndex(index)

        index = self.pattern_size_dropdown.findText(str(settings.pattern_size), flags=Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.pattern_size_dropdown.setCurrentIndex(index)

        for i, color in enumerate(settings.pattern_colors):
            if i < len(self.pattern_color_rows):
                self.pattern_color_rows[i].import_settings(ColorRowData(f"Pattern Color {i+1}", color))

        index = self.weathering_dropdown.findText(str(settings.weathering), flags=Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.weathering_dropdown.setCurrentIndex(index)

    def export_settings(self):
        settings = ColoringSectionData(self.name_label.text())
        for color_row in self.color_rows:
            settings.color_rows.append(color_row.export_settings())

        settings.pattern_size = self.pattern_size_dropdown.currentText()
        settings.pattern_number = self.pattern_dropdown.currentText()

        for pattern_color_row in self.pattern_color_rows:
            settings.pattern_colors.append(QColor(pattern_color_row.color_picker.palette().button().color()))

        settings.weathering = self.weathering_dropdown.currentText()

        return settings

def save_id_to_equipment_id(save_id_bytes):
    """
    Convert a save ID back to its original equipment ID and category.
    :param save_id_bytes: The save ID bytes from the save file
    :return: A tuple of (equipment_id, category)
    """
    save_id = struct.unpack('<I', save_id_bytes)[0]  # Unpack as little-endian 32-bit unsigned int
    category_value = save_id & 0xF0000000
    equipment_id = save_id & 0x0FFFFFFF
    for category, offset in CATEGORY_OFFSETS.items():
        if offset == category_value:
            return equipment_id, category

    raise ValueError(f"Unknown category offset: {category_value:08X}")


def equipment_id_to_save_id(equipment_id, category):
    """
    Convert an equipment ID to its corresponding save ID.

    :param equipment_id: The original equipment ID
    :param category: The equipment category (e.g., 'main_parts', 'generators', etc.)
    :return: The save ID as a little-endian byte string
    """
    if equipment_id == -1:
        return b'\xFF\xFF\xFF\xFF'  # Return four FF bytes

    if category not in CATEGORY_OFFSETS:
        raise ValueError(f"Unknown category: {category}")

    save_id = equipment_id + CATEGORY_OFFSETS[category]

    return struct.pack('<I', save_id)  # Pack as little-endian 32-bit unsigned int



def process_assemble_bytes(assemble_bytes):
    parts = []
    weapons = []

    # Process the first 28 bytes (7 part IDs)
    for i in range(0, 28, 4):
        part_id_bytes = assemble_bytes[i:i+4]
        equipment_id, category = save_id_to_equipment_id(part_id_bytes)
        parts.append((equipment_id, category))

    # Check the separator bytes
    separator_bytes = assemble_bytes[28:32]
    if separator_bytes != b'\xFF\xFF\xFF\xFF':
        print("Invalid separator bytes.")
        return None

    # Process the remaining 32 bytes (8 weapon IDs)
    for i in range(32, 64, 4):
        if i in [48,52,56]:  # Skip weapon 5,6,7
            continue

        weapon_id_bytes = assemble_bytes[i:i+4]
        if weapon_id_bytes == b'\xFF\xFF\xFF\xFF':
            # Empty weapon slot
            weapons.append((-1, 'weapon'))
        else:
            equipment_id, category = save_id_to_equipment_id(weapon_id_bytes)
            weapons.append((equipment_id, category))

    return parts, weapons

def process_coloring_bytes(coloring_bytes):
    coloring_sections = []
    section_index = 0

    # Process the color sets
    for i in range(14):
        start = i * 68
        end = start + 68
        color_set_bytes = coloring_bytes[start:end]

        if i in [6, 7, 9, 10, 11]:
            continue  # Skip the unknown sections
        coloring_section = ColoringSectionData.from_bytes(color_section_labels[section_index], color_set_bytes)
        coloring_sections.append(coloring_section)
        section_index += 1

    return coloring_sections

class DesignDecompressor(QWidget):
    def __init__(self):
        super().__init__()
        self.current_section = 0
        self.coloring_sections:List[ColoringSection] = []
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Design Editor')
        self.setGeometry(100, 100, 400, 400)  # Adjust the window size as needed

        layout = QVBoxLayout()

        # AC Data section
        ac_data_label = QLabel('AC Data')
        ac_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ac_data_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(ac_data_label)

        ac_data_line = QFrame()
        ac_data_line.setFrameShape(QFrame.Shape.HLine)
        ac_data_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(ac_data_line)

        ugc_id_layout = QHBoxLayout()
        ugc_id_label = QLabel('UgcID:')
        self.ugc_id_field = QLineEdit()
        ugc_id_layout.addWidget(ugc_id_label)
        ugc_id_layout.addWidget(self.ugc_id_field)
        layout.addLayout(ugc_id_layout)

        data_name_layout = QHBoxLayout()
        data_name_label = QLabel('DataName:')
        self.data_name_field = QLineEdit()
        data_name_layout.addWidget(data_name_label)
        data_name_layout.addWidget(self.data_name_field)
        layout.addLayout(data_name_layout)

        ac_name_layout = QHBoxLayout()
        ac_name_label = QLabel('AcName:')
        self.ac_name_field = QLineEdit()
        ac_name_layout.addWidget(ac_name_label)
        ac_name_layout.addWidget(self.ac_name_field)
        layout.addLayout(ac_name_layout)

        # Parts section
        parts_label = QLabel('Parts')
        parts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        parts_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(parts_label)

        parts_line = QFrame()
        parts_line.setFrameShape(QFrame.Shape.HLine)
        parts_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(parts_line)

        parts_layout = QVBoxLayout()
        part_rows = [['Head', 'Core'],
                     ['Arms', 'Legs'],
                     ['Booster', 'Generator', 'FCS']]
        self.part_fields = []
        for part_row in part_rows:
            row_layout = QHBoxLayout()
            for idx, part_name in enumerate(part_row):
                part_layout = QVBoxLayout()
                part_label = QLabel(part_name)
                part_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                part_layout.addWidget(part_label)
                part_field = QComboBox()
                part_field.setEditable(True)
                part_field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                completer = part_field.completer()
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

                part_field.setMaximumWidth(400)  # Set a maximum width for the part comboboxes
                part_layout.addWidget(part_field)
                row_layout.addLayout(part_layout)
                #if len(part_row) < 3 and idx == 0:
                #    row_layout.addStretch(1)
                self.part_fields.append(part_field)
            #row_layout.addStretch(1)
            parts_layout.addLayout(row_layout)
        layout.addLayout(parts_layout)
        self.load_parts()

        # Weapons section
        weapons_label = QLabel('Weapons')
        weapons_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        weapons_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(weapons_label)

        weapons_line = QFrame()
        weapons_line.setFrameShape(QFrame.Shape.HLine)
        weapons_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(weapons_line)

        weapons_layout = QVBoxLayout()
        weapon_rows = [
            ['Left Hand', 'Right Hand'],
            ['Left Shoulder', 'Right Shoulder'],
            ['Core Expansion']
        ]
        self.weapon_fields = []
        for weapon_row in weapon_rows:
            row_layout = QHBoxLayout()
            for weapon_name in weapon_row:
                if len(weapon_row) == 1:
                    row_layout.addStretch(1)
                weapon_layout = QVBoxLayout()
                weapon_label = QLabel(weapon_name)
                weapon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                weapon_layout.addWidget(weapon_label)
                weapon_field = QComboBox()
                weapon_field.setMaximumWidth(400)  # Set a maximum width for the part comboboxes
                weapon_field.setEditable(True)
                weapon_field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

                completer = weapon_field.completer()
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

                weapon_layout.addWidget(weapon_field)
                row_layout.addLayout(weapon_layout)
                if len(weapon_row) == 1:
                    row_layout.addStretch(1)
                self.weapon_fields.append(weapon_field)
            #row_layout.addStretch(1)
            weapons_layout.addLayout(row_layout)
        layout.addLayout(weapons_layout)
        self.load_weapons()



        # Navigation row
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton('←')
        self.prev_button.clicked.connect(self.prev_section)
        self.prev_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['primary_color']}")
        self.next_button = QPushButton('→')
        self.next_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['toggle_color']}")

        self.next_button.clicked.connect(self.next_section)

        coloring_label = QLabel('Colors')
        coloring_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coloring_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(coloring_label)
        nav_layout.addWidget(self.next_button)
        layout.addLayout(nav_layout)

        copy_all_layout = QHBoxLayout()
        copy_all_layout.addWidget(QLabel(""))
        self.copy_to_all_button = QPushButton('Copy to All')
        self.copy_to_all_button.clicked.connect(self.copy_to_all_sections)
        copy_all_layout.addWidget(self.copy_to_all_button)
        copy_all_layout.addWidget(QLabel(""))
        layout.addLayout(copy_all_layout)
        # Create coloring sections
        self.coloring_stack = QStackedWidget()
        for name in color_section_labels:
            section = ColoringSection(name)
            self.coloring_sections.append(section)
            self.coloring_stack.addWidget(section)
        layout.addWidget(self.coloring_stack)

        self.editor_widget = QWidget()
        self.editor_widget.setLayout(layout)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # Make the scroll area resizable
        self.scroll_area.setWidget(self.editor_widget)
        self.root_layout = QVBoxLayout()
        self.root_layout.addWidget(self.scroll_area)

        # Bottom row
        bottom_row_layout = QHBoxLayout()
        design_file_label = QLabel('Design File:')
        self.design_file_input = QLineEdit()
        design_file_browse_button = QPushButton('Browse')
        design_file_browse_button.clicked.connect(self.browse_design_file)
        design_file_load_button = QPushButton('Load')
        design_file_load_button.clicked.connect(self.load_design_file)
        bottom_row_layout.addWidget(design_file_label)
        bottom_row_layout.addWidget(self.design_file_input)
        bottom_row_layout.addWidget(design_file_browse_button)
        bottom_row_layout.addWidget(design_file_load_button)
        bottom_row_layout.addStretch()
        save_button = QPushButton('Save')
        save_button.clicked.connect(self.save_file)
        bottom_row_layout.addWidget(save_button)
        self.root_layout.addLayout(bottom_row_layout)

        self.setLayout(self.root_layout)
        self.fix_size()

    def fix_size(self):
        # Get screen size
        screen = QtWidgets.QApplication.primaryScreen()
        self.adjustSize()

        if not hasattr(self, "editor_widget"):
            return  # Whoops, too early.

        # Now get the sizeHint of the settings_widget and compare it with the screen size

        recommended_size = self.editor_widget.sizeHint()
        screen_size = screen.availableGeometry()
        screen_size = QtCore.QSize(int(screen_size.width() * 8 / 10), int(screen_size.height() * 8 / 10))

        # Calculate the size to set (accounting for the scroll bars)
        size_to_set = QtCore.QSize(
            min(recommended_size.width() + self.scroll_area.verticalScrollBar().width() * 3, screen_size.width()),
            min(recommended_size.height() + self.scroll_area.horizontalScrollBar().height(), screen_size.height())
        )

        # Set the size of the dialog
        self.resize(size_to_set)

    def prev_section(self):
        if self.current_section > 0:
            self.current_section -= 1
            self.update_section()

    def next_section(self):
        if self.current_section < 8:
            self.current_section += 1
            self.update_section()

    def update_section(self):
        self.coloring_stack.setCurrentIndex(self.current_section)
        if self.current_section > 0:
            self.prev_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['toggle_color']}")
        else:
            self.prev_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['primary_color']}")

        if self.current_section < len(color_section_labels) - 1:
            self.next_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['toggle_color']}")
        else:
            self.next_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['primary_color']}")
        self.prev_button.setEnabled(self.current_section > 0)
        self.next_button.setEnabled(self.current_section < len(color_section_labels) - 1)

    def copy_to_all_sections(self):
        current_section = self.coloring_sections[self.current_section]
        settings = current_section.export_settings()

        for i, section in enumerate(self.coloring_sections):
            if i != self.current_section:
                # Create a new settings object with the target section's name
                new_settings = ColoringSectionData(section.name)
                # Copy all other settings from the current section
                new_settings.color_rows = settings.color_rows
                new_settings.pattern_number = settings.pattern_number
                new_settings.pattern_size = settings.pattern_size
                new_settings.pattern_colors = settings.pattern_colors
                new_settings.weathering = settings.weathering

                section.import_settings(new_settings)

        QMessageBox.information(self, "Copy Complete", "Settings copied to all sections.")

    def load_parts(self):
        part_files = [
            "data/EquipParamProtector.txt",
            "data/EquipParamProtector.txt",
            "data/EquipParamProtector.txt",
            "data/EquipParamProtector.txt",
            "data/EquipParamBooster.txt",
            "data/EquipParamGenerator.txt",
            "data/EquipParamFcs.txt"
        ]

        part_keywords = [
            "HEAD",
            "CORE",
            "ARMS",
            "LEGS",
            "",
            "",
            ""
        ]

        cwd = os.getcwd()
        for i, part_field in enumerate(self.part_fields):
            if i < len(part_files):
                with open(resource_path(part_files[i]), 'r') as file:
                    parts = [line.strip() for line in file if part_keywords[i] in line]
                    part_field.addItems(parts)

    def load_weapons(self):

        cwd = os.getcwd()
        for i, weapon_field in enumerate(self.weapon_fields):
            with open(resource_path("data/EquipParamWeapon.txt"), 'r') as file:
                weapons = [line.strip() for line in file]
                if i == 0 or i == 2:
                    weapons = [weapon for weapon in weapons if "(Right)" not in weapon]
                if i == 1 or i == 3:
                    weapons = [weapon for weapon in weapons if "(Right)" in weapon or "Fists" in weapon]
                if i == 4:
                    weapons = [weapon for weapon in weapons if "EXPANSION" in weapon]
                weapon_field.addItem("-1 Empty")
                weapon_field.addItems(weapons)

    def browse_design_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Design File', '', 'All Files (*)')
        if file_path:
            self.design_file_input.setText(file_path)
            self.load_design_file()

    def load_design_file(self):
        file_path = self.design_file_input.text()
        if file_path:
            try:
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                    if file_content.startswith(b'ASMC'):
                        decompressed_data = self.try_decompress(file_content)
                        if decompressed_data:
                            self.decompressed_data = BytesIO(decompressed_data)
                            print("Decompression successful!")
                    elif file_content.startswith(b'---- begin ----'):
                        self.decompressed_data = BytesIO(file_content)
                        print("File loaded as is.")
                    else:
                        raise ValueError("File does not start with the required bytes.")
            except FileNotFoundError as e:
                print("File not found. Please check the file path.")
                raise e
            self.read_sections()
    def try_decompress(self, data):
        try:
            # Find the position of the zlib header [0x78, 0xDA]
            start = data.find(bytes([0x78, 0xDA]))
            if start != -1:
                # Cut off the extra header
                data = data[start:]
                try:
                    decompressed_data = zlib.decompress(data)
                except zlib.error as e:
                    #Flip the last 4 bytes and try again.
                    flipped_data = data[:-4] + data[-4:][::-1]
                    try:
                        decompressed_data = zlib.decompress(flipped_data)
                    except zlib.error as ex:
                        #Okay, fuck it, we're just going to ignore the checksum.
                        raw_data = data[2:-4]
                        decompressor = zlib.decompressobj(wbits=-zlib.MAX_WBITS)
                        decompressed_data = decompressor.decompress(raw_data)
                        remaining_data = decompressor.unused_data
                        if remaining_data:
                            print("Warning: Decompression completed with remaining data.")
                            print("Remaining data:", remaining_data)


                return decompressed_data
            else:
                print("Zlib header not found.")
                return None
        except zlib.error as e:
            print(f"Decompression failed: {e}")
            raise e

    def read_sections(self):
        self.decompressed_data.seek(0)
        data = self.decompressed_data.read()

        _, ugc_id_bytes = self.read_section_value(data, b'UgcID', b'DataName')
        _, data_name_bytes = self.read_section_value(data, b'DataName', b'AcName')
        _, ac_name_bytes = self.read_section_value(data, b'AcName', b'Assemble')

        ugc_id = self.convert_to_string(ugc_id_bytes)
        data_name = self.convert_to_string(data_name_bytes)
        ac_name = self.convert_to_string(ac_name_bytes)

        self.ugc_id_field.setText(ugc_id)
        self.data_name_field.setText(data_name)
        self.ac_name_field.setText(ac_name)

        _, assemble_bytes = self.read_section_value(data, b'Assemble', b'Coloring')
        if assemble_bytes is not None:
            parts, weapons = process_assemble_bytes(assemble_bytes)
            if parts is not None and weapons is not None:
                for i, (equipment_id, category) in enumerate(parts):
                    match_found = False
                    for index in range(self.part_fields[i].count()):
                        if str(equipment_id) in self.part_fields[i].itemText(index):
                            self.part_fields[i].setCurrentIndex(index)
                            match_found = True
                            break
                    if not match_found:
                        self.part_fields[i].setEditText(f"{equipment_id}")

                for i, (equipment_id, category) in enumerate(weapons):
                    if i < len(self.weapon_fields):
                        match_found = False
                        for index in range(self.weapon_fields[i].count()):
                            if str(equipment_id) in self.weapon_fields[i].itemText(index):
                                self.weapon_fields[i].setCurrentIndex(index)
                                match_found = True
                                break
                        if not match_found:
                            self.weapon_fields[i].setEditText(f"{equipment_id}")
        else:
            print("Assemble section not found.")

        _, coloring_bytes = self.read_section_value(data, b'Coloring', b'UserImage')
        color_datas = process_coloring_bytes(coloring_bytes)
        for i in range(len(self.coloring_sections)):
            self.coloring_sections[i].import_settings(color_datas[i])

    def convert_to_string(self, value_bytes):
        if value_bytes is not None:
            # Strip trailing zero bytes
            while value_bytes and value_bytes[-1] == 0:
                value_bytes = value_bytes[:-1]

            value = ''.join(chr(b) for b in value_bytes[::2])
            return value
        else:
            return None

    def read_section_value(self, data, start_marker, end_marker):
        start_index = data.find(start_marker)
        if start_index == -1:
            return None

        end_index = data.find(end_marker)
        if end_index == -1:
            return None

        chunk_header_bytes = data[start_index:start_index + 0x20]
        chunk_header = ChunkHeader.from_bytes(chunk_header_bytes)
        value_start = start_index + 0x20
        value_bytes = data[value_start:end_index]

        # Strip trailing zero bytes
        while value_bytes and value_bytes[-1] == 0:
            value_bytes = value_bytes[:-1]

        return chunk_header, value_bytes

    def save_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save File', '', 'All Files (*)')
        if file_path:
            # Load the original file
            with open(self.design_file_input.text(), 'rb') as file:
                original_data = file.read()

            # Check if the file needs to be decompressed
            if original_data.startswith(b'ASMC'):
                original_data = self.try_decompress(original_data)
                if original_data is None:
                    raise ValueError("Decompression failed.")

            # Find the start of the "Coloring" section
            end_start = original_data.find(b'UserImage')
            if end_start == -1:
                raise ValueError("End section not found in the original file.")

            # Store everything starting at the "Coloring" section
            end_data = original_data[end_start:]

            # Create a BytesIO object to store the modified data
            modified_data = BytesIO()

            # Write the "---- begin ----" header
            begin_header = ChunkHeader('---- begin ----', 0, 0)
            modified_data.write(begin_header.to_bytes())

            # Write the UgcID section
            ugc_id_bytes = self.ugc_id_field.text().encode('utf-16-le') + b"\x00\x00"
            ugc_id_header = ChunkHeader('UgcID', len(ugc_id_bytes), 0)
            modified_data.write(ugc_id_header.to_bytes())
            modified_data.write(ugc_id_bytes)

            # Write the DataName section
            data_name_bytes = self.data_name_field.text().encode('utf-16-le') + b"\x00\x00"
            data_name_header = ChunkHeader('DataName', len(data_name_bytes), 0)
            modified_data.write(data_name_header.to_bytes())
            modified_data.write(data_name_bytes)

            # Write the AcName section
            ac_name_bytes = self.ac_name_field.text().encode('utf-16-le') + b"\x00\x00"
            ac_name_header = ChunkHeader('AcName', len(ac_name_bytes), 0)
            modified_data.write(ac_name_header.to_bytes())
            modified_data.write(ac_name_bytes)

            # Write the "Assemble" section
            assemble_data = BytesIO()

            # Write the Parts
            part_fields = [
                self.part_fields[0],  # Head
                self.part_fields[1],  # Body
                self.part_fields[2],  # Arms
                self.part_fields[3],  # Legs
                self.part_fields[4],  # Booster
                self.part_fields[5],  # Generator
                self.part_fields[6]  # FCS
            ]

            part_categories = ["body_part", "body_part", "body_part", "body_part", "booster", "generator", "fcs"]
            for idx, part_field in enumerate(part_fields):
                part_id = int(part_field.currentText().split(' ')[0].strip())
                assemble_data.write(equipment_id_to_save_id(part_id, part_categories[idx]))

            assemble_data.write(b'\xFF\xFF\xFF\xFF')

            # Write the Weapons
            weapon_fields = [
                self.weapon_fields[0],  # Left Hand
                self.weapon_fields[1],  # Right Hand
                self.weapon_fields[2],  # Left Shoulder
                self.weapon_fields[3],  # Right Shoulder
                299300,  # Hardcoded value
                299100,  # Hardcoded value
                -1,  # Placeholder for the four FF bytes
                self.weapon_fields[4]  # Core Expansion
            ]
            for weapon_field in weapon_fields:
                if weapon_field == -1:
                    assemble_data.write(b'\xFF\xFF\xFF\xFF')
                else:
                    if isinstance(weapon_field, int):
                        weapon_id = weapon_field
                    else:
                        weapon_id = int(weapon_field.currentText().split(' ')[0].strip())
                    assemble_data.write(equipment_id_to_save_id(weapon_id, 'weapon'))

            assemble_header = ChunkHeader('Assemble', len(assemble_data.getvalue()), 3)
            modified_data.write(assemble_header.to_bytes())
            modified_data.write(assemble_data.getvalue())

            # Write the color sets
            color_set_data = BytesIO()
            for i, section in enumerate(self.coloring_sections):
                section_data_bytes = section.export_settings().to_bytes()
                color_set_data.write(section_data_bytes)
                # Write dummy data for unknown sections
                if i == 4:  # After Right weapon
                    for _ in range(2):
                        color_set_data.write(section_data_bytes)  # Repeat Right weapon data
                elif i == 7:  # After Left weapon
                    for _ in range(3):
                        color_set_data.write(section_data_bytes)  # Repeat Left weapon data

            # Update the "Coloring" header with the actual length
            coloring_header = ChunkHeader('Coloring', len(color_set_data.getvalue()), 3)
            modified_data.write(coloring_header.to_bytes())
            # Write the color set data
            modified_data.write(color_set_data.getvalue())

            # Write the stored end data (UserImage and beyond)
            modified_data.write(end_data)

            # Save the modified data to the selected file path
            with open(file_path, 'wb') as file:
                file.write(modified_data.getvalue())

            print(f"File saved as: {file_path}")


if __name__ == '__main__':
    colors_dict = {
        "primary_color": "#1A1D22",
        "secondary_color": "#282C34",
        "hover_color": "#596273",
        "text_color": "#FFFFFF",
        "toggle_color": "#4a708b",
        "green": "#3a7a3a",
        "yellow": "#faf20c",
        "red": "#7a3a3a"
    }
    stylesheet = """* {
    background-color: {primary_color};
    color: {secondary_color};
}

QLabel {
    color: {text_color};
}
QMenu {
    color: {text_color};
}
QLineEdit {
    background-color: {secondary_color};
    color: {text_color};
    border: 1px solid {hover_color};
}

QPushButton {
    background-color: {secondary_color};
    color: {text_color};
}

QPushButton:hover {
    background-color: {hover_color};
}

QCheckBox::indicator:unchecked {
    color: {hover_color};
    background-color: {secondary_color};
}

QCheckBox::indicator:checked {
    color: {hover_color};
    background-color: {primary_color};
}

QComboBox {
    background-color: {secondary_color};
    color: {text_color};
    border: 1px solid {hover_color};
}

QAbstractItemView {
    background-color: {secondary_color};
    color: {text_color};
}

QMessageBox {
    background-color: {primary_color};
    color: {text_color};
}

QProgressBar {
        border: 0px solid {hover_color};
        text-align: center;
        background-color: {secondary_color};
        color: {text_color};
}
QProgressBar::chunk {
    background-color: {toggle_color};
}


QScrollBar {
    background: {primary_color};
    border: 2px {text_color};
}
QScrollBar::handle {
    background: {toggle_color};
}

QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
}

QFrame[frameShape="4"] {
    background-color: {hover_color};
}
    """

    for colorKey, colorValue in colors_dict.items():
        stylesheet = stylesheet.replace("{" + colorKey + "}", colorValue)

    app = QApplication([])

    app.setStyleSheet(stylesheet)
    decompressor = DesignDecompressor()
    decompressor.show()
    app.exec()