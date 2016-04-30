'''
Requirement psuedocode:
@author: bdadson
PREAMBLE:   Install VLAN on switches for customers.
            Customer specific 802.1ad VLAN in TOR(Top of Rack),
            using multi switch ports segregation via Q-in-Q. 
KEY:
....................    
s0        = Switch 0
port1     = port 0
cust      = customer
....................
(def:
value_pair=({
            'cust1'    :    ['s1-eth1', 's1-eth2', 's3-eth3'],
            'cust2'    :    ['s2-eth1', 's2-eth2', 's1-eth3'],
            'cust3'    :    ['s3-eth1', 's3_eth2', 's2-eth3'],
            'trunk'    :    ['s1-eth4', 's2-eth4', 's3-eth4']
})
loop until value_pair.end() |key|
(
  (if key like 'cust')
  {
    ((MATCH):
        +(INSTRUCTIONS)
        {
            +(WRITE_ACTIONS)
                push-VLAN
                    +(ACTION_LIST)
                        [push 0x88a8 , push 0x8100]
            -(CLEAR_ACTION)
            -(WRITE_ACTION)
            -(GOTO_ACTION)
         }.add_to_flow(..)
    }
       
    
  (if key like 'trunk')
  {
    ((MATCH):
        +(INSTRUCTIONS)
        {
            +(APPLY_ACTIONS)
                push-VLAN
                    +(ACTION_LIST)
                        [push 0x88a8]
            -(CLEAR_ACTION)
            -(WRITE_ACTION)
            -(GOTO_ACTION)
         }.add_to_flow(..)
    }
))
'''
from ryu.base import app_manager
from ryu.ofproto import ether, ofproto_v1_3, inet
from ryu.controller import dpset, ofp_event
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.lib.mac import haddr_to_str

import logging
import struct

logger = logging.getLogger(__name__)

# static VLAN Ethertypes for testing
VLAN_TAG_802_1Q = 0x8100  
BRIDGE_TAG_802_1AD = 0x88A8
        
class VLan_Proactive(app_manager.RyuApp):
    _CONTEXTS = {'dpset': dpset.DPSet}
    # Set version 1.3 Open Flow
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    value_pair = {'tenda1'    :    ['s1-eth1', 's1-eth3', 's2-eth2'],
                  'tenda2'    :    ['s1-eth2', 's2-eth1', 's3-eth1'],
                  'trunk'    :    ['s1-eth4', 's2-eth3', 's3-eth2']}
            
    def __init__(self, *_args, **_kvargs):
       super(VLan_Proactive, self).__init__(*_args, **_kvargs)

    '''
    Add  a new flow entry to the the switch flow table
    '''
    def _add_flow(self, datapath, match, actions):
        inst = [datapath.ofproto_parser.OFPInstructionActions(
            datapath.ofproto.OFPIT_APPLY_ACTIONS, actions)]

        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath, cookie=0, cookie_mask=0, table_id=0,
            command=datapath.ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=0xff, buffer_id=0xffffffff,
            out_port=datapath.ofproto.OFPP_ANY, out_group=datapath.ofproto.OFPG_ANY,
            flags=0, match=match, instructions=inst)
        
        datapath.send_msg(mod)
        
    def build_match(self, datapath, port):
        match = datapath.ofproto_parser.OFPMatch()
        match.set_in_port(port)
        match.set_dl_type(ether.ETH_TYPE_IP)
        return match

    '''
    VLAN
    Add 801.2Q tag
    Ethertype: 0x8100
    '''
    def tag_vlan(self, port, vlan_id, datapath):
        match = self.build_match(datapath, port)
        match.set_vlan_vid(vlan_id)

        field = datapath.ofproto_parser.OFPMatchField.make(
            datapath.ofproto.OXM_OF_VLAN_VID, vlan_id)
        actions = [datapath.ofproto_parser.OFPActionPushVlan(VLAN_TAG_802_1Q),
                   datapath.ofproto_parser.OFPActionSetField(field)]
        self._add_flow(datapath, match, actions)
    

    def tag_customer_vlan(self, labels, vlan_id, datapath):
         port = self._get_port_number(labels, datapath)
         if port is not None:
            logger.debug("--- Tagging port=> %s with VLAN ID => %s with Label => %s",
                         port.port_no, vlan_id, port.name)
            self.tag_vlan(port.port_no, vlan_id, datapath)    
    
    '''
    TRUNK
    Add 801.1AD tag
    Ethertype: 0x88a8
    '''
    def tag_trunk(self, port, trunk_id, datapath):
        match = self.build_match(datapath, port)
                
        actions = [datapath.ofproto_parser.OFPActionPushVlan(BRIDGE_TAG_802_1AD)]
        self._add_flow(datapath, match, actions)
    
    def tag_trunk_vlan(self, labels, trunk_id, datapath):
        port = self._get_port_number(labels, datapath)
        if port is not None:
            logger.debug("--- Tagging port=> %s with TRUNK_ID => %s with Label => %s",
                         port.port_no, trunk_id, port.name)
            self.tag_trunk(port.port_no, trunk_id, datapath)

    #########################################################
    #Get port number. Ex: Port ID of port H1 ?
    def _get_port_number(self, labels, datapath):

        def is_switch_label(label):
            #for k, port in datapath.ports.items():
            for port in datapath.ofproto.port_no:
                if label in port.name:
                    return port
            return None
    
        for label in labels:
            port = is_switch_label(label) 
            if port is not None:
                return port 
        return None
    ##########################################################
    def install_vpn_flow(self, datapath):
        # Static value of customer and aggregated switch ports
        # Note this value is use purposely for test only        
        trunk_id = 1
        for key, labels in reversed(self.value_pair.items()):
            if 'tenda1' in key:
                vlan_id = 1
                self.tag_customer_vlan(labels, vlan_id, datapath)
            elif 'tenda2' in key:
                vlan_id = 2
                self.tag_customer_vlan(labels, vlan_id, datapath)
            elif 'trunk' in key:
                trunk_id += 1
                self.tag_trunk_vlan(labels, trunk_id, datapath)

        logger.info("")
    
    '''
    Install DataPath event dispatcher to invoke this method,
    anytime there's event dispatched to the DataPath from controller.
    '''
    #@set_ev_cls(dpset.EventDP, dpset.DPSET_EV_DISPATCHER)
    #@set_ev_cls(dpset.EventDP, CONFIG_DISPATCHER)
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def handler_datapath(self, event):
        #if event.enter:
        logger.info("++++++ Installing VLAN ++++++")
             #logger.info(event.dp.ports)
        self.install_vpn_flow(event.msg.datapath)


    # @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    # def packet_in_handler(self, ev):
    #     msg = ev.msg
    #     dst, src, eth_type = struct.unpack_from('!6s6sH', buffer(msg.data), 0)
    #
    #     match = msg.match.fields
    #     for field in match:
    #         logger.info("FIELDS==> %s ",field.value)
    #
    #     logger.info("")
#        logger.info("----------------------------------------")
#        logger.info("* PacketIn")
#        logger.info("in_port=%d, eth_type: %s", in_port, hex(eth_type))
#        logger.info("packet reason=%d buffer_id=%d", msg.reason, msg.buffer_id)
#        logger.info("packet in datapath_id=%s src=%s dst=%s",
#                 msg.datapath.id, haddr_to_str(src), haddr_to_str(dst))
