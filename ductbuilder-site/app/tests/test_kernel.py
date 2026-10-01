import unittest

from airkan_builder.kernel import Kernel


class _Box:
    XMin = 1
    YMin = 2
    ZMin = 3
    XMax = 4
    YMax = 5
    ZMax = 6


class _FreeCADShape:
    def __init__(self):
        self.arguments = None

    def optimalBoundingBox(self, use_triangulation, use_shape_tolerance):
        self.arguments = (use_triangulation, use_shape_tolerance)
        return _Box()


class _BaseKernel:
    def bounds(self, shape):
        return [7, 8, 9, 10, 11, 12]


class KernelTests(unittest.TestCase):
    def test_freecad_bounds_use_exact_physical_envelope(self):
        kernel = Kernel.__new__(Kernel)
        kernel.backend = "freecad"
        kernel.base = _BaseKernel()
        shape = _FreeCADShape()

        self.assertEqual(kernel.bounds(shape), [1, 2, 3, 4, 5, 6])
        self.assertEqual(shape.arguments, (False, False))

    def test_non_freecad_bounds_delegate_to_vendor_kernel(self):
        kernel = Kernel.__new__(Kernel)
        kernel.backend = "cadquery"
        kernel.base = _BaseKernel()

        self.assertEqual(kernel.bounds(object()), [7, 8, 9, 10, 11, 12])


if __name__ == "__main__":
    unittest.main()