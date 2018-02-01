from Qt import QtCore
from Qt import QtGui
from Qt.QtWidgets import QGraphicsWidget
from Qt.QtWidgets import QMenu
from Qt.QtWidgets import QApplication
from AbstractGraph import *
from Settings import *
import nodes_res_rc
import pyrr


_PINS = {}


class _Pin(QGraphicsWidget, PinBase):
    '''
    This is base class for all ui pins
    '''

    OnPinConnected = QtCore.Signal(object)
    OnPinDisconnected = QtCore.Signal(object)
    dataBeenSet = QtCore.Signal(object)

    def __init__(self, name, parent, dataType, direction, **kwargs):
        QGraphicsWidget.__init__(self)
        PinBase.__init__(self, name, parent, dataType, direction, **kwargs)
        self.setParentItem(parent)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.menu = QMenu()
        self.actionDisconnect = self.menu.addAction('Disconnect all')
        self.actionDisconnect.triggered.connect(self.disconnectAll)
        self.actionCopyUid = self.menu.addAction('copy uid')
        self.actionCopyUid.triggered.connect(self.saveUidToClipboard)
        self.newPos = QtCore.QPointF()
        self.setFlag(QGraphicsWidget.ItemSendsGeometryChanges)
        self.setCacheMode(self.DeviceCoordinateCache)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        self.width = 8 + 1
        self.height = 8 + 1
        self.hovered = False
        self.startPos = None
        self.endPos = None
        self._container = None
        self._execPen = QtGui.QPen(Colors.Exec, 0.5, QtCore.Qt.SolidLine)
        self.setGeometry(0, 0, self.width, self.height)
        self._dirty_pen = QtGui.QPen(Colors.DirtyPen, 0.5, QtCore.Qt.DashLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)

        self.pinImage = QtGui.QImage(':/icons/resources/array.png')
        self.bLabelHidden = False
        self.bAnimate = False
        self.val = 0
        self.setData(self.defaultValue())

    def setData(self, value):
        PinBase.setData(self, value)
        self.dataBeenSet.emit(value)

    def highlight(self):
        self.bAnimate = True
        t = QtCore.QTimeLine(900, self)
        t.setFrameRange(0, 100)
        t.frameChanged[int].connect(self.animFrameChanged)
        t.finished.connect(self.animationFinished)
        t.start()

    def animFrameChanged(self, value):
        self.width = clamp(math.sin(self.val) * 9, 4.5, 25)
        self.update()
        self.val += 0.1

    def animationFinished(self):
        self.width = 9
        self.update()
        self.val = 0

    @staticmethod
    def color():
        return QtGui.QColor()

    def call(self):
        PinBase.call(self)

    def kill(self):
        PinBase.kill(self)
        self.disconnectAll()
        if hasattr(self.parent(), self.name):
            delattr(self.parent(), self.name)
        if self._container is not None:
            self.parent().graph().scene().removeItem(self._container)
            if self.direction == PinDirection.Input:
                self.parent().inputsLayout.removeItem(self._container)
            else:
                self.parent().outputsLayout.removeItem(self._container)

    @staticmethod
    def deserialize(owningNode, jsonData):
        name = jsonData['name']
        dataType = jsonData['dataType']
        direction = jsonData['type']
        value = jsonData['value']
        uid = uuid.UUID(jsonData['uuid'])
        bLabelHidden = jsonData['bLabelHidden']
        bDirty = jsonData['bDirty']

        p = None
        if direction == PinDirection.Input:
            p = owningNode.addInputPin(name, dataType, hideLabel=bLabelHidden)
            p.uid = uid
        else:
            p = owningNode.addOutputPin(name, dataType, hideLabel=bLabelHidden)
            p.uid = uid

        p.setData(value)
        return p

    def serialize(self):
        data = {'name': self.name,
                'dataType': self.dataType,
                'type': self.direction,
                'value': self.currentData(),
                'uuid': str(self.uid),
                'bLabelHidden': self.bLabelHidden,
                'bDirty': self.dirty
                }
        return data

    def ungrabMouseEvent(self, event):
        super(_Pin, self).ungrabMouseEvent(event)

    def get_container(self):
        return self._container

    def boundingRect(self):
        if not self.dataType == DataTypes.Exec:
            return QtCore.QRectF(0, -0.5, 8 * 1.5, 8 + 1.0)
        else:
            return QtCore.QRectF(0, -0.5, 10 * 1.5, 10 + 1.0)

    def sizeHint(self, which, constraint):
        return QtCore.QSizeF(self.width, self.height)

    def saveUidToClipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.clear()
        clipboard.setText(str(self.uid))

    def disconnectAll(self):
        trash = []
        for e in self.edge_list:
            if self.uid == e.destination().uid:
                trash.append(e)
            if self.uid == e.source().uid:
                trash.append(e)
        for e in trash:
            self.parent().graph().removeEdge(e)
        self.bEdgeTangentDirection = False

    def shape(self):
        path = QtGui.QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter, option, widget):
        background_rect = QtCore.QRectF(0, 0, self.width, self.width)

        w = background_rect.width() / 2
        h = background_rect.height() / 2

        linearGrad = QtGui.QRadialGradient(QtCore.QPointF(w, h), self.width / 2.5)
        if not self._connected:
            linearGrad.setColorAt(0, self.color().darker(280))
            linearGrad.setColorAt(0.5, self.color().darker(280))
            linearGrad.setColorAt(0.65, self.color().lighter(130))
            linearGrad.setColorAt(1, self.color().lighter(70))
        else:
            linearGrad.setColorAt(0, self.color())
            linearGrad.setColorAt(1, self.color())

        if self.hovered:
            linearGrad.setColorAt(1, self.color().lighter(200))
        if self.dataType == DataTypes.Array:
            if self.pinImage:
                painter.drawImage(background_rect, self.pinImage)
            else:
                painter.setBrush(Colors.Array)
                rect = background_rect
                painter.drawRect(rect)
        elif self.dataType == DataTypes.Exec:
            painter.setPen(self._execPen)
            if self._connected:
                painter.setBrush(QtGui.QBrush(self.color()))
            else:
                painter.setBrush(QtCore.Qt.NoBrush)
            arrow = QtGui.QPolygonF([QtCore.QPointF(0.0, 0.0),
                                    QtCore.QPointF(self.width / 2.0, 0.0),
                                    QtCore.QPointF(self.width, self.height / 2.0),
                                    QtCore.QPointF(self.width / 2.0, self.height),
                                    QtCore.QPointF(0, self.height)])
            painter.drawPolygon(arrow)
        else:
            painter.setBrush(QtGui.QBrush(linearGrad))
            painter.drawEllipse(background_rect)
            arrow = QtGui.QPolygonF([QtCore.QPointF(self.width, self.height * 0.7),
                                    QtCore.QPointF(self.width * 1.15, self.height / 2.0),
                                    QtCore.QPointF(self.width, self.height * 0.3),
                                    QtCore.QPointF(self.width, self.height * 0.7)])
            painter.drawPolygon(arrow)

    def contextMenuEvent(self, event):
        self.menu.exec_(event.screenPos())

    def getLayout(self):
        if self.direction == PinDirection.Input:
            return self.parent().inputsLayout
        else:
            return self.parent().outputsLayout

    def hoverEnterEvent(self, event):
        super(_Pin, self).hoverEnterEvent(event)
        self.update()
        self.hovered = True
        self.setToolTip(str(self.currentData()))
        event.accept()

    def hoverLeaveEvent(self, event):
        super(_Pin, self).hoverLeaveEvent(event)
        self.update()
        self.hovered = False

    def pinConnected(self, other):
        PinBase.pinConnected(self, other)
        self.OnPinConnected.emit(other)

    def pinDisconnected(self, other):
        PinBase.pinDisconnected(self, other)
        self.OnPinDisconnected.emit(other)


###############################
# # Custom pins implementations
###############################


class FloatPin(_Pin):
    """doc string for FloatPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(FloatPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(0.0)

    @staticmethod
    def color():
        return Colors.Float

    @staticmethod
    def pinDataType():
        return DataTypes.Float, 0.0

    def supportedDataTypes(self):
        return (DataTypes.Float, DataTypes.Int)

    def setData(self, data):
        try:
            self._data = float(data)
        except:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class IntPin(_Pin):
    """doc string for IntPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(IntPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(0)

    @staticmethod
    def color():
        return Colors.Int

    @staticmethod
    def pinDataType():
        return DataTypes.Int, 0

    def supportedDataTypes(self):
        return (DataTypes.Int, DataTypes.Float)

    def setData(self, data):
        try:
            self._data = int(data)
        except:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class ExecPin(_Pin):
    """doc string for ExecPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(ExecPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.width = self.height = 10.0
        self.dirty = False

    def supportedDataTypes(self):
        return (DataTypes.Exec,)

    def call(self):
        super(ExecPin, self).call()
        # pass execution flow forward
        for p in [pin for pin in self.affects if pin.dataType == DataTypes.Exec]:
            p.call()
        # highlight wire
        for e in self.edge_list:
            e.highlight()

    @staticmethod
    def color():
        return Colors.Exec

    @staticmethod
    def pinDataType():
        return DataTypes.Exec, None

    def setData(self, data):
        pass


class StringPin(_Pin):
    """doc string for StringPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(StringPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue("")

    def supportedDataTypes(self):
        return (DataTypes.String,)

    @staticmethod
    def color():
        return Colors.String

    @staticmethod
    def pinDataType():
        return DataTypes.String, ''

    def setData(self, data):
        try:
            self._data = str(data)
        except:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class ListPin(_Pin):
    """doc string for ListPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(ListPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue([])

    def supportedDataTypes(self):
        return (DataTypes.Array,)

    @staticmethod
    def color():
        return Colors.Array

    @staticmethod
    def pinDataType():
        return DataTypes.Array, []

    def setData(self, data):
        if isinstance(data, list):
            self._data = data
        else:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class BoolPin(_Pin):
    """doc string for BoolPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(BoolPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(False)

    def supportedDataTypes(self):
        return (DataTypes.Bool,)

    @staticmethod
    def color():
        return Colors.Bool

    @staticmethod
    def pinDataType():
        return DataTypes.Bool, False

    def setData(self, data):
        try:
            self._data = bool(data)
        except:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class FloatVector3Pin(_Pin):
    """doc string for FloatVector3Pin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(FloatVector3Pin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(pyrr.Vector3())

    def supportedDataTypes(self):
        return (DataTypes.FloatVector3,)

    @staticmethod
    def color():
        return Colors.FloatVector3

    @staticmethod
    def pinDataType():
        return DataTypes.FloatVector3, pyrr.Vector3()

    def serialize(self):
        data = _Pin.serialize(self)
        data['value'] = self.currentData().xyz.tolist()
        return data

    def setData(self, data):
        if isinstance(data, pyrr.Vector3):
            self._data = data
        elif isinstance(data, list) and len(data) == 3:
            self._data = pyrr.Vector3(data)
        else:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class FloatVector4Pin(_Pin):
    """doc string for FloatVector4Pin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(FloatVector4Pin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(pyrr.Vector4())

    def supportedDataTypes(self):
        return (DataTypes.FloatVector4,)

    @staticmethod
    def pinDataType():
        return DataTypes.FloatVector4, pyrr.Vector4()

    @staticmethod
    def color():
        return Colors.FloatVector4

    def serialize(self):
        data = _Pin.serialize(self)
        data['value'] = self.currentData().xyzw.tolist()
        return data

    def setData(self, data):
        if isinstance(data, pyrr.Vector4):
            self._data = data
        elif isinstance(data, list) and len(data) == 4:
            self._data = pyrr.Vector4(data)
        else:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class QuatPin(_Pin):
    """doc string for QuatPin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(QuatPin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(pyrr.Quaternion())

    def supportedDataTypes(self):
        return (DataTypes.Quaternion,)

    @staticmethod
    def color():
        return Colors.Quaternion

    @staticmethod
    def pinDataType():
        return DataTypes.Quaternion, pyrr.Quaternion()

    def serialize(self):
        # note how custom class can be serialized
        # here we store quats xyzw as list
        data = _Pin.serialize(self)
        data['value'] = self.currentData().xyzw.tolist()
        return data

    def setData(self, data):
        if isinstance(data, pyrr.Quaternion):
            self._data = data
        elif isinstance(data, list) and len(data) == 4:
            # here serialized data will be handled
            # when node desirializes itself, it creates all pins
            # and then sets data to them. Here, data will be set fo the first time after deserialization
            self._data = pyrr.Quaternion(data)
        else:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class Matrix33Pin(_Pin):
    """doc string for Matrix33Pin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(Matrix33Pin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(pyrr.Matrix33())

    def supportedDataTypes(self):
        return (DataTypes.Matrix33,)

    @staticmethod
    def color():
        return Colors.Matrix33

    @staticmethod
    def pinDataType():
        return DataTypes.Matrix33, pyrr.Matrix33()

    def serialize(self):
        data = _Pin.serialize(self)
        m = self.currentData()
        data['value'] = [m.c1.tolist(), m.c2.tolist(), m.c3.tolist()]
        return data

    def setData(self, data):
        if isinstance(data, pyrr.Matrix33):
            self._data = data
        elif isinstance(data, list) and len(data) == 3:
            self._data = pyrr.Matrix33([data[0], data[1], data[2]])
        else:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)


class Matrix44Pin(_Pin):
    """doc string for Matrix44Pin"""
    def __init__(self, name, parent, dataType, direction, **kwargs):
        super(Matrix44Pin, self).__init__(name, parent, dataType, direction, **kwargs)
        self.setDefaultValue(pyrr.Matrix44())

    def supportedDataTypes(self):
        return (DataTypes.Matrix44,)

    @staticmethod
    def color():
        return Colors.Matrix44

    @staticmethod
    def pinDataType():
        return DataTypes.Matrix44, pyrr.Matrix44()

    def serialize(self):
        data = _Pin.serialize(self)
        m = self.currentData()
        data['value'] = [m.c1.tolist(), m.c2.tolist(), m.c3.tolist(), m.c4.tolist()]
        return data

    def setData(self, data):
        if isinstance(data, pyrr.Matrix44):
            self._data = data
        elif isinstance(data, list) and len(data) == 4:
            self._data = pyrr.Matrix44([data[0], data[1], data[2], data[3]])
        else:
            self._data = self.defaultValue()
        _Pin.setData(self, self._data)

# put classes by dataType
for subclass in _Pin.__subclasses__():
    # put data types in dict
    _PINS[subclass.pinDataType()[0]] = subclass


def findPinClassByType(dataType):
        return _PINS[dataType] if dataType in _PINS else None


def CreatePin(name, parent, dataType, direction):
    '''
    this function will be used by node
    '''
    # if dataType == DataTypes.Float:
    #     return FloatPin(name, parent, dataType, direction)
    # if dataType == DataTypes.Int:
    #     return IntPin(name, parent, dataType, direction)
    # if dataType == DataTypes.Exec:
    #     return ExecPin(name, parent, dataType, direction)
    # if dataType == DataTypes.String:
    #     return StringPin(name, parent, dataType, direction)
    # if dataType == DataTypes.Array:
    #     return ListPin(name, parent, dataType, direction)
    # if dataType == DataTypes.Bool:
    #     return BoolPin(name, parent, dataType, direction)
    # if dataType == DataTypes.FloatVector3:
    #     return FloatVector3Pin(name, parent, dataType, direction)
    # if dataType == DataTypes.FloatVector4:
    #     return FloatVector4Pin(name, parent, dataType, direction)
    # if dataType == DataTypes.Quaternion:
    #     return QuatPin(name, parent, dataType, direction)
    # if dataType == DataTypes.Matrix33:
    #     return Matrix33Pin(name, parent, dataType, direction)
    # if dataType == DataTypes.Matrix44:
    #     return Matrix44Pin(name, parent, dataType, direction)

    # return None

    pinClass = findPinClassByType(dataType)
    if pinClass is None:
        return None
    inst = pinClass(name, parent, dataType, direction)
    return inst
