import os
from gzip import GzipFile
import pathlib
import multiprocessing as mp
from bidict import bidict
from jackdaw import logger
from jackdaw.dbmodel.adtrust import JackDawADTrust
from jackdaw.dbmodel.adcomp import JackDawADMachine
from jackdaw.dbmodel.aduser import JackDawADUser
from jackdaw.dbmodel.adgroup import JackDawADGroup
from jackdaw.dbmodel.adinfo import JackDawADInfo
from jackdaw.dbmodel.graphinfo import JackDawGraphInfo
from jackdaw.dbmodel.edge import JackDawEdge
from jackdaw.dbmodel.edgelookup import JackDawEdgeLookup
from jackdaw.dbmodel import windowed_query
from jackdaw.nest.graph.graphdata import GraphData, GraphNode
from jackdaw.nest.graph.construct import GraphConstruct
from jackdaw.wintypes.well_known_sids import get_name_or_sid, get_sid_for_name
import tempfile
from tqdm import tqdm
from sqlalchemy import func
import graph_tool
from graph_tool.topology import all_shortest_paths, shortest_path


class JackDawDomainGraphGrapthTools:
	def __init__(self, dbsession, graph_id, work_dir = None):
		self.dbsession = dbsession
		self.graph_id = graph_id
		self.constructs = {}
		self.graph = None
		self.domain_sid = None
		self.domain_id = None
		self.lookup = {}
		self.work_dir = work_dir

	def __resolv_edge_types(self, src_id, dst_id):
		t = []
		for res in self.dbsession.query(JackDawEdge.label).distinct(JackDawEdge.label).filter_by(graph_id = self.graph_id).filter(JackDawEdge.ad_id == self.domain_id).filter(JackDawEdge.src == src_id).filter(JackDawEdge.dst == dst_id).all():
			t.append(res)
		return t

	def __resolve_sid_to_id(self, sid):
		for res in self.dbsession.query(JackDawEdgeLookup.id).filter_by(ad_id = self.domain_id).filter(JackDawEdgeLookup.oid == sid).first():
			return res
		return None

	def __nodename_to_sid(self, node_name):
		node_name = int(node_name)
		if node_name in self.lookup:
			return self.lookup[node_name]
		t = self.dbsession.query(JackDawEdgeLookup).get(node_name) #node_name is the ID of the edgelookup
		self.lookup[node_name] = (t.oid, t.otype)
		return t.oid, t.otype		

	def save(self):
		pass

	def load(self):
		self.graph_id = int(self.graph_id)
		graphinfo = self.dbsession.query(JackDawGraphInfo).get(self.graph_id)
		domaininfo = self.dbsession.query(JackDawADInfo).get(graphinfo.ad_id)
		self.domain_sid = domaininfo.objectSid
		self.domain_id = domaininfo.id

		create_file = False
		graph_file = None
		if self.work_dir is not None:
			graph_dir = pathlib.Path(self.work_dir).joinpath(str(self.graph_id))
			graph_dir.mkdir(parents=True, exist_ok=True)
			graph_file = graph_dir.joinpath('edges.csv')
			if graph_file.exists() is False:
				create_file = True
			else:
				logger.debug('Loading graph from file: %s' % graph_file)
		
		if create_file is True:
			logger.debug('Creating a new graph file: %s' % graph_file)

			## remove this
			fi = self.dbsession.query(JackDawEdgeLookup.id).filter_by(ad_id = self.domain_id).filter(JackDawEdgeLookup.oid == 'S-1-5-32-545').first()
			fi = fi[0]
			##

			t2 = self.dbsession.query(func.count(JackDawEdge.id)).filter_by(graph_id = self.graph_id).filter(JackDawEdgeLookup.id == JackDawEdge.src).filter(JackDawEdgeLookup.oid != None).scalar()
			q = self.dbsession.query(JackDawEdge).filter_by(graph_id = self.graph_id).filter(JackDawEdgeLookup.id == JackDawEdge.src).filter(JackDawEdgeLookup.oid != None)

			with open(graph_file, 'w', newline = '') as f:
				for edge in tqdm(windowed_query(q,JackDawEdge.id, 10000), desc = 'edge', total = t2):
					if edge.src  == fi:
						continue
					if edge.dst  == fi:
						continue
					r = '%s,%s\r\n' % (edge.src, edge.dst)
					f.write(r)

		self.graph = graph_tool.load_graph_from_csv(str(graph_file), directed=True, string_vals=False, hashed=False)

		logger.debug('Graph created!')

	def all_shortest_paths(self, src_sid = None, dst_sid = None):
		nv = GraphData()
		if src_sid is None and dst_sid is None:
			raise Exception('src_sid or dst_sid must be set')
		elif src_sid is None and dst_sid is not None:
			dst = self.__resolve_sid_to_id(dst_sid)
			if dst is None:
				raise Exception('SID not found!')
			
			total = self.dbsession.query(func.count(JackDawEdgeLookup.id)).filter_by(ad_id = self.domain_id).filter(JackDawEdgeLookup.oid != self.domain_sid + '-513').scalar()
			q = self.dbsession.query(JackDawEdgeLookup.id).filter_by(ad_id = self.domain_id).filter(JackDawEdgeLookup.oid != self.domain_sid + '-513')
			for nodeid in tqdm(windowed_query(q, JackDawEdgeLookup.id, 1000), desc = 'running', total = total):
				for path in all_shortest_paths(self.graph, nodeid[0], dst):
					print(path)
					self.__result_path_add(nv, path)

				
		#elif src_sid is not None and dst_sid is None:
		#	src = self.__resolve_sid_to_id(dst_sid)
		#	if src is None:
		#		raise Exception('SID not found!')
		#	
		#	for path in all_shortest_paths(self.graph, src, mode= self.graph.OUT):
		#		self.__result_path_add(nv, path)

		elif src_sid is not None and dst_sid is not None:
			print(1)
			print(src_sid)
			print(dst_sid)
			src = self.__resolve_sid_to_id(src_sid)
			if src is None:
				raise Exception('SID not found!')
			
			dst = self.__resolve_sid_to_id(dst_sid)
			if dst is None:
				raise Exception('SID not found!')
			
			print(src)
			print(dst)

			for path in all_shortest_paths(self.graph, src, dst):
				print(path)
				self.__result_path_add(nv, path)

		return nv

	def shortest_paths(self, src_sid = None, dst_sid = None):
		nv = GraphData()
		if src_sid is None and dst_sid is None:
			raise Exception('src_sid or dst_sid must be set')
		elif src_sid is None and dst_sid is not None:
			dst = self.__resolve_sid_to_id(dst_sid)
			if dst is None:
				raise Exception('SID not found!')


			total = self.dbsession.query(func.count(JackDawEdgeLookup.id)).filter_by(ad_id = self.domain_id).filter(JackDawEdgeLookup.oid != self.domain_sid + '-513').scalar()
			q = self.dbsession.query(JackDawEdgeLookup.id).filter_by(ad_id = self.domain_id).filter(JackDawEdgeLookup.oid != self.domain_sid + '-513')
			for nodeid in tqdm(windowed_query(q, JackDawEdgeLookup.id, 1000), desc = 'running', total = total):
				for i, res in enumerate(shortest_path(self.graph, nodeid, dst)):
					if res == []:
						continue
					if i % 2 == 0:
						self.__result_path_add(nv, res)


		elif src_sid is not None and dst_sid is not None:
			dst = self.__resolve_sid_to_id(dst_sid)
			if dst is None:
				raise Exception('SID not found!')

			src = self.__resolve_sid_to_id(src_sid)
			if src is None:
				raise Exception('SID not found!')
			
			for i, res in enumerate(shortest_path(self.graph, src, dst)):
				if res == []:
					continue
				if i % 2 == 0:
					self.__result_path_add(nv, res)
		
		else:
			raise Exception('Not implemented!')

		return nv
	
	def __result_path_add(self, network, path):
		if path == []:
			return
		path = [i for i in path]
		delete_this = []
		for d, node_id in enumerate(path):
			sid, otype = self.__nodename_to_sid(node_id)
			delete_this.append('%s(%s) -> ' % (sid, otype))
			network.add_node(
				sid, 
				name = self.__sid2cn(sid, otype), 
				node_type = otype,
				domainid = self.domain_id
			)
			network.nodes[sid].set_distance(d)

		print(''.join(delete_this))
		for i in range(len(path) - 1):
			self.__result_edge_add(network, int(path[i]), int(path[i+1]))

	def __result_edge_add(self, network, src_id, dst_id):
		for label in self.__resolv_edge_types(src_id, dst_id):
				try:
					src = self.__nodename_to_sid(src_id)
					dst = self.__nodename_to_sid(dst_id)
					network.add_edge(src[0],dst[0], label=label[0])
					print('%s -> %s [%s]' % (src, dst, label))
				except Exception as e:
					import traceback
					traceback.print_exc()
					print(e)

	def __sid2cn(self, sid, otype):
		if otype == 'user':
			tsid = self.dbsession.query(JackDawADUser.cn).filter(JackDawADUser.objectSid == sid).first()
			if tsid is not None:
				return tsid[0]
		
		elif otype == 'group':
			tsid = self.dbsession.query(JackDawADGroup.cn).filter(JackDawADGroup.objectSid == sid).first()
			if tsid is not None:
				return tsid[0]

		elif otype == 'machine':
			tsid = self.dbsession.query(JackDawADMachine.cn).filter(JackDawADMachine.objectSid == sid).first()
			if tsid is not None:
				return tsid[0]

		elif otype == 'trust':
			tsid = self.dbsession.query(JackDawADTrust.cn).filter(JackDawADTrust.securityIdentifier == sid).first()
			if tsid is not None:
				return tsid[0]
		
		else:
			return None

	def get_domainsids(self):
		pass

	def get_nodes(self):
		pass

	def get_distances_from_node(self):
		pass