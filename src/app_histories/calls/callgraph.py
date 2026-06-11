# c/o https://github.com/androguard/androguard/issues/464
# todo put into GEXF or similar. 
# Also look at graph merging
from androguard.misc import AnalyzeAPK
from androguard.core.analysis.analysis import ExternalMethod
import matplotlib.pyplot as plt
import networkx as nx

def callgraph(apk_name)
    a, d, dx = AnalyzeAPK(apk_name)

    CFG = nx.DiGraph()


    for m in dx.find_methods(classname="Lcom/elite/MainActivity;"):
        orig_method = m.get_method()
        print("Found Method --> {}".format(orig_method))
        # orig_method might be a ExternalMethod too...
        # so you can check it here also:
        if isinstance(orig_method, ExternalMethod):
            is_this_external = True
            # If this class is external, there will be very likely
            # no xref_to stored! If there is, it is probably a bug in androguard...
        else:
            is_this_external = False

        CFG.add_node(orig_method, external=is_this_external)

        for other_class, callee, offset in m.get_xref_to():
            if isinstance(callee, ExternalMethod):
                is_external = True
            else:
                is_external = False

            if callee not in CFG.node:
                CFG.add_node(callee, external=is_external)

            # As this is a DiGraph and we are not interested in duplicate edges,
            # check if the edge is already in the edge set.
            # If you need all calls, you probably want to check out MultiDiGraph
            if not CFG.has_edge(orig_method, callee):
                CFG.add_edge(orig_method, callee)

    pos = nx.spring_layout(CFG)

    internal = []
    external = []

    for n in CFG.node:
        if isinstance(n, ExternalMethod):
            external.append(n)
        else:
            internal.append(n)


    nx.draw_networkx_nodes(CFG, pos=pos, node_color='r', nodelist=internal)
    nx.draw_networkx_nodes(CFG, pos=pos, node_color='b', nodelist=external)
    nx.draw_networkx_edges(CFG, pos, arrow=True)
    nx.draw_networkx_labels(CFG, pos=pos, labels={x: "{} {}".format(x.get_class_name(), x.get_name()) for x in CFG.edge})
    plt.draw()
    plt.savefig(apk_name + ".png")

if __name__ == '__main__':
    extracted = "ab"
    if not os.path.exists(extracted): 
        os.mkdir(extracted)

    basedir = ""
    apks = glob(basedir + "/*.apk")
    with Pool(5) as p:
        p.map(callgraph, apks)