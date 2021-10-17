from math import floor
from typing import Dict, List

from autobridge.Opt.DataflowGraph import Vertex, Edge
from autobridge.Opt.GlobalRouting import GlobalRouting
from autobridge.Opt.Slot import Slot
from autobridge.Opt.Floorplan import Floorplanner

VITIS_HIERARCHY_ADDRESS = 'pfm_top_i/dynamic_region/.*/inst/'


def create_pblocks(slot_list: List[Slot]) -> List[str]:
  tcl = []
  for slot in slot_list:
    tcl.append(f'create_pblock {slot.getRTLModuleName()}')
    tcl.append(f'resize_pblock {slot.getRTLModuleName()} -add {{ {slot.getName()} }}')
    
    # TODO: subtract the vitis area
    
  return tcl


def gen_constraints_for_vertices(s2v: Dict[Slot, List[Vertex]]) -> List[str]:
  tcl = []
  for slot, v_list in s2v.items():
    tcl.append(f'add_cells_to_pblock {slot.getRTLModuleName()} [ get_cells -regexp {{ ')
    for v in v_list:
      tcl.append(f'  {VITIS_HIERARCHY_ADDRESS}/{v.name}')
    tcl.append(f'}} ]')

  return tcl


def gen_constraints_for_almost_full_fifos(s2e: Dict[Slot, List[Edge]]) -> List[str]:
  tcl = []
  for slot, e_list in s2e.items():
    tcl.append(f'add_cells_to_pblock {slot.getRTLModuleName()} [ get_cells -regexp {{ ')
    for e in e_list:
      if e.latency == 0:
        tcl.append(f'  {VITIS_HIERARCHY_ADDRESS}/{e.name}')
    tcl.append(f'}} ]')

  return tcl


def gen_constraints_for_relay_stations(
    s2e: Dict[Slot, List[Edge]],
    v2s: Dict[Vertex, Slot],
    global_router: GlobalRouting,
) -> List[str]:
  """
  assign each pipeline stage of the relay station to one slot
  """
  tcl = []
  for e_list in s2e.values():
    for e in e_list:
      if e.latency == 0:
        continue

      slot_path = global_router.e_name2path[e.name]  # exclude src and dst
      slot_path_with_src_and_dst = [ v2s[e.src], *slot_path, v2s[e.dst] ]

      slot_crossing_num = len(slot_path) + 1
      pipeline_level = e.latency  # note that latency == 0 means no additional pipelining
      assert pipeline_level == slot_crossing_num * 2, 'check if the pipeline policy has changed'

      for i in range(slot_crossing_num):
        tcl.append(f'add_cell_to_pblock {slot_path_with_src_and_dst[i].getRTLModuleName()} [get_cells -regexp {{ {VITIS_HIERARCHY_ADDRESS}/{e.name}/inst.*{2*i}.*unit }}]')
        tcl.append(f'add_cell_to_pblock {slot_path_with_src_and_dst[i+1].getRTLModuleName()} [get_cells -regexp {{ {VITIS_HIERARCHY_ADDRESS}/{e.name}/inst.*{2*i+1}.*unit }}]')

  return tcl


def generate_floorplan_constraints(floorplan: Floorplanner, global_router: GlobalRouting):
  tcl = []

  slot_list = list(floorplan.getSlotToVertices().keys())
  tcl += create_pblocks(slot_list)

  tcl += gen_constraints_for_vertices(floorplan.getSlotToVertices())

  tcl += gen_constraints_for_almost_full_fifos(floorplan.getSlotToEdges())

  tcl += gen_constraints_for_relay_stations(floorplan.getSlotToEdges(), floorplan.getVertexToSlot(), global_router)

  open('constraint.tcl', 'w').write('\n'.join(tcl))