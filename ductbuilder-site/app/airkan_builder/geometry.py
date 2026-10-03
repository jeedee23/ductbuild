"""Physical geometry. All dimensions mm. No documents or disk writes here."""
from __future__ import annotations
import math
from functools import lru_cache
from copy import deepcopy
from .kernel import Kernel, frame_api, plus, minus, scale, normalized, length, ry, dot, cross3
from .rules import resolve, profile_for, profile_depth, need, InputError, CAT, VERSION
from .pricing import complete_rectangular_geometry_price, nonstandard_frame_surcharge_count

@lru_cache(maxsize=20)
def cached_frame(backend,profile,a,b):
    return frame_api()['build_frame_geometry'](profile=profile,length=a,width=b,backend=backend)

class Build:
    def __init__(self,data,backend,progress):
        self.data=data; self.p=data['params']; self.d=data['derived']
        self.K=Kernel(backend); self.parts=[]; self.ports=[]; self.frames=[];self.air_points=[]
        self.progress=progress or (lambda message:None)
        self.extra={}
    def add(self,name,shape,code=None,group='body',body=True):
        self.parts.append(dict(name=name,shape=shape,code=code or self.data['order']['catalogue_family_code'],role=group,single_body=body))
    def port(self,name,center,normal,a=None,b=None,diameter=None,x_axis=None,kind='MATING'):
        normal=normalized(normal)
        if x_axis is None:x_axis=(0,0,1) if abs(normal[0])>.99 else (1,0,0)
        x_axis=normalized(minus(x_axis,scale(normal,dot(x_axis,normal))))
        y_axis=normalized(cross3(normal,x_axis))
        self.ports.append(dict(name=name,point_mm=list(center),x_axis=list(x_axis),y_axis=list(y_axis),z_axis=list(normal),
            width_mm=a,height_mm=b,diameter_mm=diameter,kind=kind,meaning='Outward normal; point and axes in component coordinates, millimetres'))
    def selected_profile(self,a,b):
        return profile_for(a,b) if self.p.get('frames','PROJECT_AUTO')=='PROJECT_AUTO' else 'GEEN'
    def frame(self,name,a,b,center,angle=0,profile=None):
        pr=profile or self.selected_profile(a,b)
        if pr=='GEEN':return 0.0
        self.progress(name+': '+pr+' / '+('H40' if pr=='A40' else 'H30'))
        geo=cached_frame(self.K.backend,pr,float(a),float(b))
        for part in geo['parts']:
            s=self.K.move(part['shape'],(-a/2,-b/2,0))
            s=self.K.place_y(s,angle,center)
            self.add(name+'_'+part['name'],s,part['code'],name,False)
        self.frames.append(dict(name=name,profile=pr,corner=geo['config']['corner'],inside_mm=[a,b],center_mm=list(center),
            rotation_y_deg=angle,profile_depth_mm=geo['config']['profile_depth'],validation=geo['validation'],assumptions=geo['assumptions']))
        return geo['config']['profile_depth']
    def insertion(self):return self.p.get('insertion_mm',0) if self.p.get('insertion_mode')=='HANDMATIGE_INSTEEK' else 0
    def depth(self,a,b):return profile_depth(self.selected_profile(a,b))
    def test_air(self,*points):self.air_points.extend(points)


def make_frame(g):
    p=g.p;a,b=p['a_mm'],p['b_mm'];dep=g.frame('K1',a,b,(a/2,b/2,0))
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b)
    g.port('JO_DUCT_ENTRY',(a/2,b/2,dep),(0,0,1),a,b,kind='PROFILE_ENTRY_NOT_SEATED_SHEET')


def make_bu(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];dep=g.depth(a,b);t=g.d['t_mm'];i=g.insertion()
    L=p['length_mm'] if p['length_basis']=='FLENSVLAKKEN' else p['length_mm']+2*dep
    clear=L-2*dep
    need(clear>0, 'L is too short: flange distance must be greater than two profile depths.')
    g.add('Kanaalplaat',k.rect_tube(a,b,t,clear+2*i,(0,0,dep-i)))
    g.frame('K1',a,b,(a/2,b/2,0));g.frame('K2',a,b,(a/2,b/2,L),180)
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b);g.port('JO_OUT',(a/2,b/2,L),(0,0,1),a,b)
    g.test_air((a/2,b/2,L/2))
    g.extra.update(flange_to_flange_mm=L,profile_entry_to_entry_mm=clear,plate_axial_length_mm=clear+2*i,plate_insertion_mm=i)
    g.data['order']['effective_length_mm']=L


def make_rect_bend(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];t=g.d['t_mm'];dep=g.depth(a,b);i=g.insertion()
    si,so,R=p['straight_in_mm'],p['straight_out_mm'],p['radius_mm'];th=g.d['angle_deg']
    z0=dep+si;axis=(a+R if th>0 else -R,0,z0);mid=(a/2,b/2,z0)
    ow=k.rectangle(a+2*t,b+2*t,mid);iw=k.rectangle(a,b,mid)
    arc=k.cut(k.revolve_wire(ow,axis,(0,1,0),th),k.revolve_wire(iw,axis,(0,1,0),th))
    inlet=k.rect_tube(a,b,t,si+i,(0,0,dep-i))
    outlet=k.rect_tube(a,b,t,so+i,(0,0,z0));outlet=k.rotate(outlet,(0,1,0),th,axis)
    core=k.fuse([inlet,arc,outlet]);g.add('Kanaalplaat_bocht',core)
    arc_end=plus(axis,ry(minus(mid,axis),th));dout=ry((0,0,1),th)
    c2=plus(arc_end,scale(dout,so+dep))
    g.frame('K1',a,b,(a/2,b/2,0));g.frame('K2',a,b,c2,th+180)
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b)
    g.port('JO_OUT',c2,dout,a,b,x_axis=ry((1,0,0),th))
    g.test_air(plus(axis,ry(minus(mid,axis),th/2)),(a/2,b/2,dep+si/2),plus(arc_end,scale(dout,so/2)))
    g.extra.update(revolve_axis_point_mm=axis,revolve_axis_direction=[0,1,0],tangent_plane_z_mm=z0,inner_air_radius_mm=R,
        centerline_radius_mm=R+a/2,angle_deg=abs(th),straight_in_mm=si,straight_out_mm=so,
        tangent_axis_axial_offset_mm=0.0,literal_two_offset_planes_status='NOT_USED_WITHOUT_REFERENCE_PLANES; an axial 150 mm offset at the end section is not tangent',
        dimension_map={'A':'in bend plane XZ','B':'normal to bend plane, parallel to revolve axis Y'},outlet_center_mm=c2)


def make_transition(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];t=g.d['t_mm'];i=g.insertion();L=p['length_mm']
    if p['family']=='VER':c,d=a,b;e,f=p['offset_x_mm'],p['offset_y_mm']
    else:c,d=p['c_mm'],p['d_mm'];e,f=g.d['e_mm'],g.d['f_mm']
    dp,dq=g.depth(a,b),g.depth(c,d);si,so=p['straight_in_mm'],p['straight_out_mm']
    z0,z1=dp+si,L-dq-so
    need(z1>z0,'L te kort voor kaders en rechte aansluitstukken.')
    centers=[(a/2,b/2,z0),(e+c/2,f+d/2,z1)]
    outer=k.loft([k.rectangle(a+2*t,b+2*t,centers[0]),k.rectangle(c+2*t,d+2*t,centers[1])],True)
    inner=k.loft([k.rectangle(a,b,centers[0]),k.rectangle(c,d,centers[1])],True)
    chunks=[k.cut(outer,inner)]
    if si+i>0:chunks.append(k.rect_tube(a,b,t,si+i,(0,0,dp-i)))
    if so+i>0:chunks.append(k.rect_tube(c,d,t,so+i,(e,f,z1)))
    g.add('Kanaalplaat_transfo',k.fuse(chunks))
    g.frame('K1',a,b,(a/2,b/2,0));g.frame('K2',c,d,(e+c/2,f+d/2,L),180)
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b);g.port('JO_OUT',(e+c/2,f+d/2,L),(0,0,1),c,d)
    g.test_air(scale(plus(centers[0],centers[1]),.5))
    g.extra.update(flange_to_flange_mm=L,loft_length_mm=z1-z0,offset_edge_x_mm=e,offset_edge_y_mm=f,
        wall_model='section offsets; not normal sheet thickness on tapered faces')


def make_rect_round(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];d=p['diameter_mm'];t=g.d['t_mm'];i=g.insertion();L=p['length_mm']
    dp=g.depth(a,b);si,so=p['straight_in_mm'],p['straight_out_mm'];z0,z1=dp+si,L-so
    need(z1>z0,'L te kort voor kader en rechte aansluitstukken.')
    c0=(a/2,b/2,z0);c1=(a/2+p['offset_x_mm'],b/2+p['offset_y_mm'],z1)
    ow=[k.rectangle(a+2*t,b+2*t,c0),k.circle(d/2+t,c1)];iw=[k.rectangle(a,b,c0),k.circle(d/2,c1)]
    pieces=[k.cut(k.loft(ow,False),k.loft(iw,False))]
    if si+i>0:pieces.append(k.rect_tube(a,b,t,si+i,(0,0,dp-i)))
    if so>0:pieces.append(k.tube(d+2*t,d,so,c1))
    g.add('Kanaalplaat_vierkant_rond',k.fuse(pieces));g.frame('K1',a,b,(a/2,b/2,0))
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b);g.port('JO_OUT',(c1[0],c1[1],L),(0,0,1),diameter=d)
    g.test_air(scale(plus(c0,c1),.5))
    g.extra.update(flange_to_round_end_mm=L,loft_length_mm=z1-z0,wall_model='smooth coordination loft; section offsets')


def make_tee(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];t=g.d['t_mm'];L=p['length_mm'];ba=p['branch_a_mm'];bl=p['branch_length_mm'];zc=p['branch_z_mm'];r=p['shoulder_radius_mm']
    need(g.insertion()==0,'Project-T ondersteunt voorlopig alleen BOM_REFERENTIE zonder insteek.')
    dp=g.depth(a,b);bp=g.depth(ba,b);z0,z1=dp,L-dp;zl,zr=zc-ba/2,zc+ba/2;xe=a+bl
    need(zl>z0 and zr<z1,'Aftakking valt buiten het rechte hoofdkanaal.')
    need(r<.44*min(zl-z0,z1-zr,bl) or r==0,'Schouderradius past niet zonder verkleining: verleng de vrije afstanden.')
    need(r==0 or r>t,'Shoulder radius must be greater than sheet thickness, or explicitly 0.')
    innerpts=[(0,z0),(a,z0),(a,zl),(xe,zl),(xe,zr),(a,zr),(a,z1),(0,z1)]
    outerpts=[(-t,z0),(a+t,z0),(a+t,zl-t),(xe,zl-t),(xe,zr+t),(a+t,zr+t),(a+t,z1),(-t,z1)]
    radii=[0,0,r,0,0,r,0,0];ro=[0,0,max(0,r-t),0,0,max(0,r-t),0,0]
    outer=k.polygon(outerpts,b+2*t,plane='XZ',origin=(0,-t,0),radius=ro)
    inner=k.polygon(innerpts,b,plane='XZ',origin=(0,0,0),radius=radii)
    g.add('Kanaalplaat_T',k.cut(outer,inner))
    g.frame('K1',a,b,(a/2,b/2,0));g.frame('K2',a,b,(a/2,b/2,L),180)
    g.frame('K3',ba,b,(xe+bp,b/2,zc),-90)
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b);g.port('JO_OUT',(a/2,b/2,L),(0,0,1),a,b)
    g.port('JO_BRANCH',(xe+bp,b/2,zc),(1,0,0),ba,b,x_axis=(0,0,1))
    g.test_air((a/2,b/2,zc),(a+bl/2,b/2,zc))
    g.extra['supported_T_variant']='constant main section, same transverse B, +X branch, 90 degrees only'


def make_takeoff(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];t=g.d['t_mm'];L=p['length_mm'];v=p['variant'];i=g.insertion()
    if v=='P.BI':
        # Inputs remain FREE opening after the 20 mm inward return.
        aa,bb=a+40,b+40;h=L;dep=0
        shell=k.rect_tube(aa,bb,t,h,(-20,-20,0))
        lip=k.cut(k.box(aa+2*t,bb+2*t,t,(-20-t,-20-t,h-t)),k.box(a,b,t+2,(0,0,h-t-1)))
        base=k.rect_tube(aa,bb,25,t,(-20,-20,0))
        core=k.fuse([shell,lip,base]);base_center=(a/2,b/2,0)
        g.data['warnings'].append('P.BI: A/B zijn vrije maten NA de 20 mm binnenomslag; basisopening is A+40 x B+40. Expliciete modelinterpretatie.')
        g.port('JO_MOUNT',base_center,(0,0,-1),aa,bb,kind='HOST_CUTOUT');g.port('JO_OUT',(a/2,b/2,L),(0,0,1),a,b)
    else:
        dep=g.depth(a,b);h=L-dep
        need(h>0,'L te kort voor kaderdiepte.')
        e=h if v=='P.45' else 0
        c0=((a-e)/2,b/2,0);c1=(a/2,b/2,h+i)
        # P.45 wall angle is based on clear height, with final straight insertion added separately.
        ow=[k.rectangle(a+e+2*t,b+2*t,c0),k.rectangle(a+2*t,b+2*t,(a/2,b/2,h))]
        iw=[k.rectangle(a+e,b,c0),k.rectangle(a,b,(a/2,b/2,h))]
        body=k.cut(k.loft(ow,True),k.loft(iw,True))
        base=k.rect_tube(a+e,b,25,t,(-e,0,0))
        chunks=[body,base]
        if i:chunks.append(k.rect_tube(a,b,t,i,(0,0,h)))
        core=k.fuse(chunks)
        g.frame('K1',a,b,(a/2,b/2,L),180)
        g.port('JO_MOUNT',c0,(0,0,-1),a+e,b,kind='HOST_CUTOUT');g.port('JO_OUT',(a/2,b/2,L),(0,0,1),a,b)
    g.add('Aftakking_plaat',core);g.test_air((a/2,b/2,L/2))


def make_s(g):
    p=g.p;d=p['diameter_mm'];L=p['length_mm'];t=g.d['t_mm']
    g.add('Spiraalbuis_glad',g.K.tube(d+2*t,d,L))
    g.port('JO_IN',(0,0,0),(0,0,-1),diameter=d);g.port('JO_OUT',(0,0,L),(0,0,1),diameter=d)
    g.test_air((0,0,L/2));g.extra.update(spiral_seam_modeled=False,physical_length_mm=L)


def make_round_bend(g):
    p=g.p;k=g.K;d=p['diameter_mm'];t=g.d['t_mm'];R=g.d['radius_mm'];N=int(p['segments']);theta=math.radians(g.d['angle_deg']);delta=theta/(N-1)
    directions=[(math.sin(j*delta),0,math.cos(j*delta)) for j in range(N)]
    pend=(R*(1-math.cos(theta)),0,R*math.sin(theta))
    nodes=[(0,0,-p['straight_in_mm'])]
    for j in range(1,N):
        ang=(j-.5)*delta;rad=R/math.cos(delta/2)
        nodes.append((R-rad*math.cos(ang),0,rad*math.sin(ang)))
    nodes.append(plus(pend,scale(directions[-1],p['straight_out_mm'])))
    big=10*(R+d+p['straight_in_mm']+p['straight_out_mm']+1)
    outer=[];inner=[]
    for j,di in enumerate(directions):
        start,end=nodes[j],nodes[j+1];le=length(minus(end,start))
        if le<=1e-8:raise InputError('Een segment heeft nul lengte.')
        ns=di if j==0 else normalized(plus(directions[j-1],di))
        ne=di if j==N-1 else normalized(plus(di,directions[j+1]))
        for diam,bucket in [(d+2*t,outer),(d,inner)]:
            cyl=k.cyl(diam,le+2*big,minus(start,scale(di,big)),di)
            cyl=k.clip_positive(cyl,start,ns,big*2)
            cyl=k.clip_positive(cyl,end,scale(ne,-1),big*2)
            bucket.append(cyl)
        g.test_air(scale(plus(start,end),.5))
    g.add('Gesegmenteerde_bocht',k.cut(k.fuse(outer),k.fuse(inner)))
    g.port('JO_IN',nodes[0],(0,0,-1),diameter=d)
    g.port('JO_OUT',nodes[-1],directions[-1],diameter=d,x_axis=ry((1,0,0),g.d['angle_deg']))
    g.extra.update(centerline_radius_mm=R,segments=N,segment_axes=directions,centerline_nodes_mm=nodes,angle_deg=g.d['angle_deg'],swept_torus=False)


def make_reg(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm']
    g.add('Registerklep_BOM',k.rect_tube(a,b,30,120))
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b);g.port('JO_OUT',(a/2,b/2,120),(0,0,1),a,b)
    g.test_air((a/2,b/2,60));g.extra.update(depth_mm=120,border_mm=30,lamellae_modeled=False,actuator_modeled=False)


def make_sl_rect(g):
    p=g.p;k=g.K;a,b=p['a_mm'],p['b_mm'];L=p['length_mm'];t=p['visual_wall_mm'];pr=g.d['profile'];h=40 if pr=='A40' else 30;dep=profile_depth(pr)
    pieces=[k.rect_tube(a,b,t,L),k.rect_tube(a,b,h,dep),k.rect_tube(a,b,h,dep,(0,0,L-dep))]
    g.add('Soepele_mouw_BOM',k.fuse(pieces))
    g.port('JO_IN',(a/2,b/2,0),(0,0,-1),a,b);g.port('JO_OUT',(a/2,b/2,L),(0,0,1),a,b)
    g.test_air((a/2,b/2,L/2));g.extra.update(mounted_length_mm=L,frame_detail='single-body simplified envelope, not the detailed frame solids')


def make_flex_round(g):
    p=g.p;d=p['diameter_mm'];L=p['length_mm'];od=p['outer_diameter_mm']
    g.add('Compensator_BOM',g.K.tube(od,d,L))
    g.port('JO_IN',(0,0,0),(0,0,-1),diameter=d);g.port('JO_OUT',(0,0,L),(0,0,1),diameter=d)
    g.test_air((0,0,L/2))


def make_connector(g):
    p=g.p;d=p['actual_id_mm'];od=p['actual_od_mm'];L=p['length_mm']
    g.add('Verbinding_BOM',g.K.tube(od,d,L))
    g.port('JO_IN',(0,0,0),(0,0,-1),diameter=d);g.port('JO_OUT',(0,0,L),(0,0,1),diameter=d)
    g.test_air((0,0,L/2));g.extra.update(nominal_diameter_mm=p['diameter_mm'],actual_id_mm=d,actual_od_mm=od,fit_insertion_depth='not inferred')


def make_flange(g):
    p=g.p;k=g.K;r=g.d['flange'];ID=r['bore_mm'];OD=ID+2*r['strip_width_mm'];t=r['thickness_mm'];N=r['hole_count'];pcd=r['pitch_mm']
    s=k.tube(OD,ID,t);holes=[]
    for j in range(N):
        th=p['hole_clock_deg']+360*j/N;ar=math.radians(th);cx=pcd/2*math.cos(ar);cy=pcd/2*math.sin(ar)
        hole=k.slot(r['slot_length_mm'],r['slot_width_mm'],t+2,(cx,cy),th+90,origin=(0,0,-1))
        s=k.cut(s,hole);holes.append((cx,cy,t/2))
    g.add('Flens_F',s);g.port('JO_IN',(0,0,0),(0,0,-1),diameter=ID);g.port('JO_OUT',(0,0,t),(0,0,1),diameter=ID)
    g.test_air(*holes,(0,0,t/2));g.extra.update(slot_centers_mm=holes,slots_verified=len(holes),**r)


def make_cover(g):
    p=g.p;k=g.K;od=p['actual_od_mm'];L=p['length_mm'];t=p['visual_wall_mm'];id_=od-2*t;v=p['variant']
    need(L>t,'Cover upstand must be greater than the visual sheet thickness.')
    tube=k.tube(od,id_,L)
    if v in ('DG','DFG'):
        cross=[k.box(od,t,t,(-od/2,-t/2,L-t)),k.box(t,od,t,(-t/2,-od/2,L-t))]
        cross=[k.common(s,k.cyl(od,t,(0,0,L-t))) for s in cross]
        core=k.fuse([tube]+cross)
    else:
        plate=k.cyl(od,t,(0,0,L-t));core=k.fuse([tube,plate])
        if v=='DFP':
            di,do,dl=p['drain_id_mm'],p['drain_od_mm'],p['drain_length_mm']
            core=k.cut(core,k.cyl(di,t+2,(0,0,L-t-1)))
            core=k.fuse([core,k.tube(do,di,dl,(0,0,L))])
            g.port('JO_DRAIN',(0,0,L+dl),(0,0,1),diameter=di)
    g.add('Deksel_BOM',core);g.port('JO_IN',(0,0,0),(0,0,-1),diameter=id_)
    g.extra['nominal_diameter_mm']=p['diameter_mm']


def make_inspection(g):
    p=g.p;k=g.K;a,b=g.d['outer_a_mm'],g.d['outer_b_mm'];h=p['depth_mm']
    if p['variant']=='IS235':s=k.cyl(a,h);c=(0,0,0)
    else:s=k.box(a,b,h);c=(a/2,b/2,0)
    g.add('Inspectieluik_BOM',s);g.port('JO_MOUNT',c,(0,0,-1),kind='MOUNTING_ENVELOPE')


def make_support(g):
    p=g.p;a,b=(150,100) if p['variant']=='PL150' else (300,300)
    g.add('Voetplaat_BOM',g.K.box(a,b,2));g.port('JO_MOUNT',(a/2,b/2,0),(0,0,-1),kind='MOUNTING_ENVELOPE')
    g.extra['omitted_holes']='Diameter 11 published; locations not dimensioned, therefore not invented.'


def make_hood(g):
    p=g.p;g.add('Kap_RUIMTE_ENVELOP',g.K.cyl(p['outer_diameter_mm'],p['length_mm']))
    g.port('JO_IN',(0,0,0),(0,0,-1),diameter=p['diameter_mm'],kind='ENVELOPE_CONNECTION_NOT_FREE_AIR')
    g.extra['airway_modeled']=False


def make_roof(g):
    p=g.p;k=g.K;x,y,h,d=p['base_x_mm'],p['base_y_mm'],p['length_mm'],p['actual_bore_mm']
    core=k.cut(k.box(x,y,h,(-x/2,-y/2,0)),k.cyl(d,h+2,(0,0,-1)))
    g.add('Dakstuk_RUIMTE_ENVELOP',core)
    g.port('JO_DUCT',(0,0,h),(0,0,1),diameter=d)
    angle=g.d['roof_angle_deg'];g.port('JO_ROOF',(0,0,0),ry((0,0,-1),angle),x_axis=ry((1,0,0),angle),kind='ROOF_REFERENCE_ONLY')
    g.extra.update(roof_angle_deg=angle,model='conservative hollow footprint envelope; no sheet-metal roof flashing detail')


def make_fire_grille(g):
    p=g.p
    g.add('Brandrooster_COORDINATIE_ENVELOP',g.K.box(p['b_mm'],p['h_mm'],p['depth_mm']))
    g.port('JO_WALL_A',(p['b_mm']/2,p['h_mm']/2,0),(0,0,-1),p['b_mm'],p['h_mm'],kind='PASSIVE_WALL_FACE')
    g.port('JO_WALL_B',(p['b_mm']/2,p['h_mm']/2,p['depth_mm']),(0,0,1),p['b_mm'],p['h_mm'],kind='PASSIVE_WALL_FACE')
    g.extra.update(envelope_b_mm=p['b_mm'],envelope_h_mm=p['h_mm'],coordination_depth_mm=p['depth_mm'],
                   product_geometry_modeled=False,unit_price_eur=g.d['unit_price_eur'])


def _require_native_review_kernel(g, family):
    need(
        g.K.backend == 'freecad',
        family + ' uses the native FreeCAD BRep validated against its source drawing; CadQuery is not a supported production backend for this family.',
    )


def make_round_branch_source(g):
    _require_native_review_kernel(g, 'AP / APA / PSA')
    p = g.p
    if p['variant'] == 'PSA':
        from tools.psa_fusion_saddle_review import build_psa_fusion_saddle

        fitting, dimensions = build_psa_fusion_saddle(p['d1_mm'], p['d2_mm'], g.d['asymmetry_mm'])
        branch_end_z_mm = dimensions['d2_spigot_height_mm']
    else:
        from tools.apa_review import build_apa

        fitting, dimensions = build_apa(p['d1_mm'], p['d2_mm'], g.d['asymmetry_mm'], p['e_mm'])
        branch_end_z_mm = dimensions['straight_spigot_end_z_mm']
    g.add('Ronde_zadelaftakking', fitting)
    branch_x_mm = dimensions['d1_center_x_mm'] if p['variant'] == 'PSA' else dimensions['d2_center_x_mm']
    g.port('JO_BRANCH', (branch_x_mm, 0.0, branch_end_z_mm), (0, 0, 1), diameter=p['d2_mm'])
    g.port(
        'HOST_CUTOUT_REFERENCE',
        (branch_x_mm, 0.0, 0.0),
        (0, 0, -1),
        diameter=p['d1_mm'],
        kind='CURVED_HOST_REFERENCE_NOT_A_MATING_PLANE',
    )
    g.extra.update(dimensions)
    g.extra.update(host_geometry='BOOLEAN_CUTTER_NOT_EXPORTED', branch_port='JO_BRANCH')


def make_rectangular_branch_source(g):
    _require_native_review_kernel(g, 'PR / PRA')
    from tools.pr_pra_review import build_pr_pra

    p = g.p
    fitting, dimensions = build_pr_pra(p['d1_mm'], p['b_mm'], p['l_mm'], g.d['asymmetry_mm'])
    g.add('Rechthoekige_zadelaftakking', fitting)
    if p['frame_profile'] != 'NO_FRAME':
        g.frame(
            'K_BRANCH',
            p['b_mm'],
            p['l_mm'],
            (g.d['asymmetry_mm'], 0.0, dimensions['branch_height_mm']),
            profile=p['frame_profile'],
        )
    g.port(
        'JO_BRANCH',
        (g.d['asymmetry_mm'], 0.0, dimensions['branch_height_mm']),
        (0, 0, 1),
        p['b_mm'],
        p['l_mm'],
    )
    g.port(
        'HOST_CUTOUT_REFERENCE',
        (g.d['asymmetry_mm'], 0.0, 0.0),
        (0, 0, -1),
        diameter=p['d1_mm'],
        kind='CURVED_HOST_REFERENCE_NOT_A_MATING_PLANE',
    )
    g.extra.update(dimensions)
    g.extra.update(host_geometry='BOOLEAN_CUTTER_NOT_EXPORTED', branch_port='JO_BRANCH')


def make_special_tee(g):
    _require_native_review_kernel(g, 'Talpha / TASYMM')
    from tools.tee_special_review import build_tee_special

    p = g.p
    variant = p['variant']
    branch_length_mm = g.d['f_mm'] if variant == 'TALPHA' else p['branch_length_mm']
    fitting, frames, dimensions = build_tee_special(
        variant,
        p['a_mm'],
        p['b_mm'],
        p['c_mm'],
        p['d_mm'],
        p['length_mm'],
        branch_length_mm,
        p['alpha_deg'],
        frame_profile=p['frame_profile'],
        e_mm=g.d.get('e_mm', 0.0),
        g_mm=p['g_mm'],
    )
    g.add(('Talpha' if variant == 'TALPHA' else 'TASYMM') + '_plaat', fitting)
    for frame_part in frames:
        port_name = frame_part['name'].split('_', 1)[0]
        g.add(frame_part['name'], frame_part['shape'], frame_part['code'], port_name, False)

    if variant == 'TALPHA':
        branch_axis = (dimensions['branch_axis_x'], 0.0, dimensions['branch_axis_z'])
        branch_width_axis = (dimensions['branch_axis_z'], 0.0, -dimensions['branch_axis_x'])
        mating_top = (
            dimensions['branch_root_x_mm'] + dimensions['branch_axis_x'] * (branch_length_mm + dimensions['frame_depth_mm']),
            dimensions['branch_root_z_mm'] + dimensions['branch_axis_z'] * (branch_length_mm + dimensions['frame_depth_mm']),
        )
        branch_center = plus(
            (mating_top[0], p['b_mm'], mating_top[1]),
            plus(scale(branch_width_axis, p['c_mm'] / 2), (0.0, -p['b_mm'] / 2, 0.0)),
        )
    else:
        branch_axis = (0.0, 0.0, 1.0)
        branch_width_axis = (1.0, 0.0, 0.0)
        branch_center = (
            dimensions['branch_root_x_mm'],
            p['b_mm'] / 2,
            dimensions['branch_root_z_mm'] + branch_length_mm,
        )
    g.port('JO_K1', (0.0, p['b_mm'] / 2, p['a_mm'] / 2), (-1, 0, 0), p['b_mm'], p['a_mm'])
    g.port('JO_K2', branch_center, branch_axis, p['c_mm'], p['b_mm'], x_axis=branch_width_axis)
    g.port('JO_K3', (p['length_mm'], p['b_mm'] / 2, p['d_mm'] / 2), (1, 0, 0), p['b_mm'], p['d_mm'])
    for port_name, height_mm in (('K1', p['a_mm']), ('K2', p['c_mm']), ('K3', p['d_mm'])):
        g.frames.append(
            dict(
                name=port_name,
                profile=p['frame_profile'],
                inside_mm=[p['b_mm'], height_mm],
                profile_depth_mm=dimensions['frame_depth_mm'],
                physical_component_count=8,
            )
        )
    physical_union = fitting.multiFuse([frame_part['shape'] for frame_part in frames]).removeSplitter()
    need(physical_union.isValid() and physical_union.Volume > 0, 'Special-tee physical assembly union is invalid.')
    g.extra.update(dimensions)
    g.extra.update(
        special_tee_variant=variant,
        k2_port='JO_K2',
        step_volume_reference_mm3=physical_union.Volume,
        step_volume_relative_tolerance=1e-4,
        step_volume_reference_note='Physical union of the sheet and 24 contacting frame solids; STEP translation tolerance is 0.01%.',
    )
    if variant == 'TALPHA':
        g.extra['talpha_contract'] = 'G is the downstream straight section; K2-to-G perpendicular clearance is at least 100 mm.'


GENERATORS={
 'FRAME':make_frame,'BU':make_bu,'BEND_RECT':make_rect_bend,'REDUCER_RECT':make_transition,'VER':make_transition,
 'RECT_ROUND':make_rect_round,'TEE_RECT':make_tee,'TAKEOFF_RECT':make_takeoff,'S':make_s,'BEND_ROUND':make_round_bend,
 'REG':make_reg,'SL_RECT':make_sl_rect,'FLEX_ROUND':make_flex_round,'CONNECTOR_ROUND':make_connector,
 'FLANGE_ROUND':make_flange,'COVER_ROUND':make_cover,'INSPECTION':make_inspection,'SUPPORT_PL':make_support,
 'HOOD':make_hood,'ROOF':make_roof,'GRILLE_FIRE':make_fire_grille,
 'AP_APA_PSA':make_round_branch_source,'PR_PRA':make_rectangular_branch_source,'TEE_SPECIAL':make_special_tee}


def build_geometry(raw,backend='freecad',progress=None):
    data=resolve(raw);g=Build(data,backend,progress);k=g.K
    g.progress('Geometrie: '+data['family_spec']['label'])
    GENERATORS[data['params']['family']](g)
    g.progress('Solids, vrije openingen en materiaaloverlap controleren')
    volumes=[]
    for p in g.parts:
        s=p['shape'];need(k.valid(s) and len(k.solids(s))==1 and k.volume(s)>0,'No valid single solid: '+p['name'])
        volumes.append(k.volume(s))
    # Preserve separate frame solids; they have already passed the original 8-component checks.
    clashes=[];pair_checks=0
    for j,a in enumerate(g.parts):
        ba=k.bounds(a['shape'])
        for b in g.parts[j+1:]:
            if a['role'].startswith('K') and a['role']==b['role']:continue
            bb=k.bounds(b['shape'])
            if not all(min(ba[m+3],bb[m+3])-max(ba[m],bb[m])>1e-6 for m in range(3)):continue
            pair_checks+=1;v=k.volume(k.common(a['shape'],b['shape']))
            if v>1e-3:clashes.append({'a':a['name'],'b':b['name'],'overlap_mm3':v})
    need(not clashes,'Materiaaloverlap; geometrie niet weggesneden om passing te forceren: '+str(clashes[:6]))
    for point in g.air_points:
        for p in g.parts:
            need(not k.inside(p['shape'],point),'Verwachte vrije luchtweg/gat is gesloten: '+str(point)+' in '+p['name'])
    for d in g.ports:
        need(abs(dot(d['x_axis'],d['z_axis']))<1e-7,'Joint-assen niet loodrecht.')
        need(dot(cross3(d['x_axis'],d['y_axis']),d['z_axis'])>.999999,'Joint-stelsel niet rechtshandig.')
    shape=k.compound([p['shape'] for p in g.parts]);bbox=k.bounds(shape)
    detail=data['family_spec']['detail']
    if detail=='BOM_SIMPLIFIED':need(len(g.parts)==1,'A simplified item must have exactly one physical Body.')
    sheet_all_faces_area_mm2=sum(k.area(part['shape']) for part in g.parts if part['single_body'])
    geometry_price=complete_rectangular_geometry_price(data['order'],sheet_all_faces_area_mm2,nonstandard_frame_surcharge_count(g.frames))
    if geometry_price:
        data['order'].update(geometry_price)
        data['derived']['pricing']=geometry_price.copy()
    validation={'backend':backend,'valid_solids':len(g.parts),'physical_objects':len(g.parts),'partdesign_body_count':sum(p['single_body'] for p in g.parts),'bounds_mm':bbox,
                'total_shape_volume_mm3':sum(volumes),'clashes':clashes,'exact_intersection_checks':pair_checks,
                'air_and_hole_sample_checks':len(g.air_points),'right_handed_ports':len(g.ports),
                'not_tested':['fabrication tolerances','seal compression','pressure resistance','complete insertion/crimp fit']}
    if 'step_volume_reference_mm3' in g.extra:
        validation.update(
            step_volume_reference_mm3=g.extra['step_volume_reference_mm3'],
            step_volume_relative_tolerance=g.extra['step_volume_relative_tolerance'],
            step_volume_reference_note=g.extra['step_volume_reference_note'],
        )
    result={'schema':'airkan-component-v3','version':VERSION,'rules_sha256':data['rules_sha256'],'units':'mm','parameters':data['params'],'derived':data['derived'],
        'filename_stem':data['filename_stem'],'order':data['order'],'detail':detail,'warnings':data['warnings'],
        'source_references':[{**r,**CAT['sources'][r['source_id']]} for r in data['family_spec']['sources']],
        'source_notes':data['family_spec']['notes'],'parts':g.parts,'shape':shape,'join_datums':g.ports,'frames':g.frames,'geometry':g.extra,
        'bom':{'quantity':1,'article':data['order']['catalogue_label'],'count_children':False,'mass_kg':None,'status':'coordination model, no mass certification'},
        'validation':validation}
    if 'unit_price_eur' in data['order']:
        result['bom'].update(unit_price_eur=data['order']['unit_price_eur'],currency='EUR',pricing_status=data['order']['pricing_status'])
    return result


def serializable(result):
    out={k:v for k,v in result.items() if k not in ('shape','parts')}
    out['model_parts']=[{k:v for k,v in p.items() if k!='shape'} for p in result['parts']]
    return out
