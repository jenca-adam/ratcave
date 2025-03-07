import numpy as np
from abc import ABCMeta, abstractmethod
from ratcave.utils.observers import IterObservable
import itertools
from operator import setitem
from scipy.spatial.transform import Rotation as R

class Coordinates(IterObservable):

    coords = {'x': 0, 'y': 1, 'z': 2}

    def __init__(self, *args, **kwargs):
        " Returns a Coordinates object"
        super(Coordinates, self).__init__(**kwargs)
        self._array = np.array(args, dtype=np.float32)
        self._init_coord_properties()

    def __repr__(self):
        arg_str = ', '.join(['{}={}'.format(*el) for el in zip('xyz', self._array)])
        return "{cls}({coords})".format(cls=self.__class__.__name__, coords=arg_str)

    def _init_coord_properties(self):
        """
        Generates combinations of named coordinate values, mapping them to the internal array.
        For Example: x, xy, xyz, y, yy, zyx, etc
        """
        def gen_getter_setter_funs(*args):
            indices = [self.coords[coord] for coord in args]

            def getter(self):
                return tuple(self._array[indices]) if len(args) > 1 else self._array[indices[0]]

            def setter(self, value):
                setitem(self._array, indices, value)
                self.notify_observers()

            return getter, setter

        for n_repeats in range(1, len(self.coords)+1):
            for args in itertools.product(self.coords.keys(), repeat=n_repeats):
                getter, setter = gen_getter_setter_funs(*args)
                setattr(self.__class__, ''.join(args), property(fget=getter, fset=setter))

    def __getitem__(self, item):
        if type(item) == slice:
            return tuple(self._array[item])
        else:
            return self._array[item]

    def __setitem__(self, idx, value):
        self._array[idx] = value
        super(Coordinates, self).__setitem__(idx, value)


class RotationBase(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def to_quaternion(self): pass

    @abstractmethod
    def to_euler(self, units='rad'): pass

    @abstractmethod
    def to_matrix(self): pass

    @classmethod
    def from_matrix(cls, matrix): pass

    def rotate(self, vector):
        """Takes a vector and returns it rotated by self."""
        return np.dot(self.to_matrix()[:3, :3], vector).flatten()


class RotationEuler(RotationBase, Coordinates):

    def __init__(self, x, y, z, axes='rxyz', **kwargs):
        super(RotationEuler, self).__init__(x, y, z, **kwargs)
        self.axes = axes


class RotationEulerRadians(RotationEuler):

    def to_radians(self):
        return self

    def to_degrees(self):
        return RotationEulerDegrees(*np.degrees(self._array), axes=self.axes)

    def to_quaternion(self):
        return RotationQuaternion(*R.from_euler(self._axes[1:],self._array,degrees=False).as_quat())

    def to_matrix(self):
        mat = np.eye(4)
        res = R.from_euler(self.axes[1:],self._array,degrees=False)
        try:
            res=res.as_matrix()#Adjusted for the newest scipy version
        except AttributeError:
            res=res.as_dcm()#Older version

        mat[:3, :3] = res 
        return mat

    def to_euler(self, units='rad'):
        assert units.lower() in ['rad', 'deg']
        if units.lower() == 'rad':
            return RotationEulerRadians(*self._array, axes=self.axes)
        else:
            return RotationEulerDegrees(*np.degrees(self._array), axes=self.axes)

    @classmethod
    def from_matrix(cls, matrix, axes='rxyz'):
        coords = R.from_matrix(matrix[:3, :3]).as_euler(axes[1:], degrees=False)
        return cls(*coords)



class RotationEulerDegrees(RotationEuler):
    def to_radians(self):
        return RotationEulerRadians(*np.radians(self._array), axes=self.axes)

    def to_degrees(self):
        return self

    def to_quaternion(self):
        return self.to_radians().to_quaternion()

    def to_euler(self, units='rad'):
        return self.to_radians().to_euler(units=units)

    def to_matrix(self):
        return self.to_radians().to_matrix()

    @classmethod
    def from_matrix(cls, matrix, axes='rxyz'):
        coords = R.from_matrix(matrix[:3, :3]).as_euler(axes[1:], degrees=True)
        return cls(*coords)

class RotationQuaternion(RotationBase, Coordinates):

    coords = {'w': 0, 'x': 1, 'y': 2, 'z': 3}

    def __init__(self, w, x, y, z, **kwargs):
        super(RotationQuaternion, self).__init__(w, x, y, z)

    def __repr__(self):
        arg_str = ', '.join(['{}={}'.format(*el) for el in zip('wxyz', self._array)])
        return "{cls}({coords})".format(cls=self.__class__.__name__, coords=arg_str)

    def to_quaternion(self):
        return self

    def to_matrix(self):
        mat = np.eye(4, 4)
        mat[:3, :3] = R.from_quat(self).as_matrix()
        return mat

    def to_euler(self, units='rad'):
        euler_data = R.from_quat(self).as_euler(axes='xyz',degrees=False)
        assert units.lower() in ['rad', 'deg']
        if units.lower() == 'rad':
            return RotationEulerRadians(*euler_data)
        else:
            return RotationEulerDegrees(*np.degrees(euler_data))

    @classmethod
    def from_matrix(cls, matrix):
        return cls(*R.from_matrix(matrix[:3, :3]).as_quat())

class Translation(Coordinates):

    def __init__(self, *args, **kwargs):
        assert len(args) == 3, "Must be xyz coordinates"
        super(Translation, self).__init__(*args, **kwargs)

    def __add__(self, other):
        oth = other.xyz if isinstance(other, Translation) else other
        if len(oth) != 3:
            raise ValueError("Other must have length of 3")
        return Translation(*tuple(a + b for (a, b) in zip(self.xyz, oth)))

    def __sub__(self, other):
        oth = other.xyz if isinstance(other, Translation) else other
        if len(oth) != 3:
            raise ValueError("Other must have length of 3")
        return Translation(*tuple(a - b for (a, b) in zip(self.xyz, other.xyz)))

    def to_matrix(self):
        mat = np.eye(4,4)
        mat[:3,3] = self._array
        return mat

    @classmethod
    def from_matrix(cls, matrix):
        """Returns a Translation from a 4x4 model matrix (the first three rows of the last column)."""
        return cls(*matrix[:3, 3])


class Scale(Coordinates):

    def __init__(self, *args, **kwargs):
        vals = args * 3 if len(args) == 1 else args
        assert len(vals) == 3, "Must be xyz coordinates"
        super(self.__class__, self).__init__(*vals, **kwargs)

    def to_matrix(self):
        return np.diag((self._array[0], self._array[1], self._array[2], 1.))

    @classmethod
    def from_matrix(cls, matrix):
        return cls(*np.linalg.norm(matrix[:3, :3], axis=0))



def cross_product_matrix(vec):
    """Returns a 3x3 cross-product matrix from a 3-element vector."""
    return np.array([[0, -vec[2], vec[1]],
                     [vec[2], 0, -vec[0]],
                     [-vec[1], vec[0], 0]])


def rotation_matrix_between_vectors(from_vec, to_vec):
    """
    Returns a rotation matrix to rotate from 3d vector "from_vec" to 3d vector "to_vec".
    Equation from https://math.stackexchange.com/questions/180418/calculate-rotation-matrix-to-align-vector-a-to-vector-b-in-3d
    """
    a, b = (vec/np.linalg.norm(vec) for vec in (from_vec, to_vec))

    v = np.cross(a, b)
    cos = np.dot(a, b)
    if cos == -1.:
        raise ValueError("Orientation in complete opposite direction")
    v_cpm = cross_product_matrix(v)
    rot_mat = np.identity(3) + v_cpm + np.dot(v_cpm, v_cpm) * (1. / 1. + cos)
    return rot_mat
