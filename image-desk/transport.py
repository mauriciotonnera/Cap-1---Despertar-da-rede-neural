"""Consistent vector transport icons and an absolute-position scrub slider."""

from qtpy.QtCore import QPointF, QRectF, Qt
from qtpy.QtGui import QColor, QPainter, QPen, QPolygonF
from qtpy.QtWidgets import QPushButton, QSlider, QStyle, QStyleOptionSlider


class TransportButton(QPushButton):
    def __init__(self, action, tooltip, callback, parent=None):
        super().__init__(parent)
        self.action = action
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5274cf" if self.isDown() else "#40506a" if self.underMouse() else "#293345"))
        p.drawEllipse(QRectF(1, 1, 38, 38))
        color = QColor("#f6f8ff" if self.isEnabled() else "#67748a")
        p.setBrush(color)
        if self.action == "pause":
            p.drawRect(QRectF(13, 12, 5, 16))
            p.drawRect(QRectF(22, 12, 5, 16))
        elif self.action == "stop":
            p.drawRect(QRectF(12, 12, 16, 16))
        elif self.action == "restart":
            p.setPen(QPen(color, 2.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(11, 11, 18, 18), 40 * 16, -285 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPolygon(QPolygonF([QPointF(11, 8), QPointF(11, 18), QPointF(19, 11)]))
        else:
            if self.action == "previous":
                points = [(26, 12), (14, 20), (26, 28)]
                p.drawRect(QRectF(10, 12, 3, 16))
            else:
                points = [(14, 11), (28, 20), (14, 29)]
                if self.action == "next":
                    points = [(12, 12), (25, 20), (12, 28)]
                    p.drawRect(QRectF(27, 12, 3, 16))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#8cacf9"), 1.5))
            p.drawEllipse(QRectF(2, 2, 36, 36))


class SeekSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setTracking(True)
        self.setAccessibleName("Media playhead")
        self.setToolTip("Drag to skim through frames. Release to restore the previous play/pause state.")

    def _at(self, event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                            QStyle.SubControl.SC_SliderHandle, self)
        span = max(1, self.width() - handle.width())
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                              event.pos().x() - handle.width() // 2, span, option.upsideDown)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setFocus()
            self.setSliderDown(True)
            self.setValue(self._at(event))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setValue(self._at(event))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setValue(self._at(event))
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
