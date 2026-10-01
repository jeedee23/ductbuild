"""Thin FreeCAD/CadQuery adapter; CadQuery is used ONLY for developer tests."""
from __future__ import annotations
import math
import runpy
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def frame_api():
    path=Path(__file__).resolve().parents[1]/'vendor'/'makeframe_v2.FCMacro'
    return runpy.run_path(str(path),init_globals={'MAKEFRAME_LIBRARY_ONLY':True})

def plus(a,b):return tuple(x+y for x,y in zip(a,b))
def minus(a,b):return tuple(x-y for x,y in zip(a,b))
def scale(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross3(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def length(a):return math.sqrt(dot(a,a))
def normalized(a):
    l=length(a)
    if l<1e-12:raise ValueError('Null vector')
    return scale(a,1/l)
def ry(p,deg):
    t=math.radians(deg);c,s=math.cos(t),math.sin(t)
    return (c*p[0]+s*p[2],p[1],-s*p[0]+c*p[2])

class Kernel:
    def __init__(self,backend='freecad'):
        self.base=frame_api()['Kernel'](backend)
        self.backend=backend
    def __getattr__(self,name):return getattr(self.base,name)
    def bounds(self,s):
        if self.backend=='freecad' and hasattr(s,'optimalBoundingBox'):
            b=s.optimalBoundingBox(False,False)
            return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
        return self.base.bounds(s)
    def area(self,s):return float(s.Area) if self.backend=='freecad' else float(s.Area())
    def common(self,a,b):return a.common(b) if self.backend=='freecad' else a.intersect(b)
    def distance(self,a,b):return a.distToShape(b)[0] if self.backend=='freecad' else a.distance(b)
    def wire3(self,pts):
        pts=list(pts)
        if pts[0]!=pts[-1]:pts.append(pts[0])
        if self.backend=='freecad':return self.P.makePolygon([self.v(p) for p in pts])
        return self.cq.Wire.makePolygon([self.v(p) for p in pts])
    def rectangle(self,a,b,center=(0,0,0)):
        x,y,z=center
        return self.wire3([(x-a/2,y-b/2,z),(x+a/2,y-b/2,z),(x+a/2,y+b/2,z),(x-a/2,y+b/2,z)])
    def circle(self,r,center=(0,0,0)):
        # Four arcs, indexed to the rectangular section corners: avoids arbitrary loft seam.
        edges=[]
        for i in range(4):
            angles=[math.radians(225+90*i+j) for j in (0,45,90)]
            ps=[self.v(plus(center,(r*math.cos(t),r*math.sin(t),0))) for t in angles]
            if self.backend=='freecad':edges.append(self.P.Arc(*ps).toShape())
            else:edges.append(self.cq.Edge.makeThreePointArc(*ps))
        return self.P.Wire(edges) if self.backend=='freecad' else self.cq.Wire.assembleEdges(edges)
    def face(self,wire):
        return self.P.Face(wire) if self.backend=='freecad' else self.cq.Face.makeFromWires(wire)
    def extrude_wire(self,wire,vec):
        if self.backend=='freecad':return self.P.Face(wire).extrude(self.v(vec))
        return self.cq.Solid.extrudeLinear(wire,[],self.v(vec))
    def loft(self,wires,ruled=False):
        if self.backend=='freecad':return self.P.makeLoft(wires,True,ruled,False)
        return self.cq.Solid.makeLoft(wires,ruled)
    def revolve_wire(self,wire,origin,axis,deg):
        # Use the same positive-angle convention on both kernels.
        if deg<0:axis=scale(axis,-1);deg=-deg
        if self.backend=='freecad':return self.P.Face(wire).revolve(self.v(origin),self.v(axis),deg)
        return self.cq.Solid.revolve(wire,[],deg,origin,plus(origin,axis))
    def rect_tube(self,a,b,t,h,origin=(0,0,0)):
        x,y,z=origin
        outer=self.box(a+2*t,b+2*t,h,(x-t,y-t,z))
        inner=self.box(a,b,h+2,(x,y,z-1))
        return self.cut(outer,inner)
    def place_y(self,s,angle,translation):
        return self.move(self.rotate(s,(0,1,0),angle),translation)
    def orient_z(self,s,normal,translation=(0,0,0)):
        normal=normalized(normal);axis=cross3((0,0,1),normal)
        c=max(-1,min(1,normal[2]))
        if length(axis)>1e-12:s=self.rotate(s,normalized(axis),math.degrees(math.acos(c)))
        elif c<0:s=self.rotate(s,(1,0,0),180)
        return self.move(s,translation)
    def clip_positive(self,s,point,normal,extent):
        box=self.box(2*extent,2*extent,2*extent,(-extent,-extent,0))
        return self.clean(self.common(s,self.orient_z(box,normal,point)))
    def export_shape(self,s,path):
        if self.backend=='freecad':s.exportStep(str(path))
        else:self.cq.exporters.export(s,str(path))
    def read_shape(self,path):
        if self.backend=='freecad':return self.P.read(str(path))
        return self.cq.importers.importStep(str(path)).val()
