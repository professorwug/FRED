# AUTOGENERATED! DO NOT EDIT! File to edit: 01c Plotting Utils.ipynb (unless otherwise specified).

__all__ = ['SmallRandom', 'plot_directed_2d', 'plot_origin_3d', 'plot_directed_3d', 'plot_3d', 'visualize_graph',
           'visualize_heatmap']

# Cell
import warnings
import torch
from torch_geometric.data import Data, InMemoryDataset
from torch_sparse import SparseTensor
from torch_geometric.utils import remove_self_loops


class SmallRandom(InMemoryDataset):
    def __init__(self, num_nodes=5, prob_edge=0.2, transform=None, pre_transform=None):
        super().__init__(".", transform, pre_transform)

        if num_nodes > 300:
            num_nodes = 300
            warnings.warn(
                f"Number of nodes is too large for SmallRandom dataset. Reset num_nodes =  {num_nodes}"
            )

        dense_adj = (torch.rand((num_nodes, num_nodes)) < prob_edge).int()
        sparse_adj = SparseTensor.from_dense(dense_adj)
        row, col, _ = sparse_adj.coo()
        edge_index, _ = remove_self_loops(torch.stack([row, col]))

        x = torch.eye(num_nodes, dtype=torch.float)
        data = Data(x=x, edge_index=edge_index)
        if self.pre_transform is not None:
            data = self.pre_transform(data)
        self.data, self.slices = self.collate([data])

# Cell
import matplotlib.pyplot as plt


def plot_directed_2d(X, flows, labels, mask_prob=0.5, cmap="viridis"):
    num_nodes = X.shape[0]
    fig = plt.figure()
    ax = fig.add_subplot()
    ax.scatter(X[:, 0], X[:, 1], marker=".", c=labels, cmap=cmap)
    mask = np.random.rand(num_nodes) > mask_prob
    ax.quiver(X[mask, 0], X[mask, 1], flows[mask, 0], flows[mask, 1], alpha=0.1)
    ax.set_aspect("equal")
    plt.show()


# Cell
def plot_origin_3d(ax, xlim, ylim, zlim):
    ax.plot(xlim, [0, 0], [0, 0], color="k", alpha=0.5)
    ax.plot([0, 0], ylim, [0, 0], color="k", alpha=0.5)
    ax.plot([0, 0], [0, 0], zlim, color="k", alpha=0.5)


def plot_directed_3d(X, flow, labels, mask_prob=0.5, cmap="virdis", origin=False):
    num_nodes = X.shape[0]
    mask = np.random.rand(num_nodes) > mask_prob
    fig = plt.figure()
    ax = fig.add_subplot(projection="3d")
    if origin:
        plot_origin_3d(
            ax,
            xlim=[X[:, 0].min(), X[:, 0].max()],
            ylim=[X[:, 1].min(), X[:, 1].max()],
            zlim=[X[:, 2].min(), X[:, 2].max()],
        )
    ax.scatter(X[:, 0], X[:, 1], X[:, 2], marker=".", c=labels, cmap=cmap)
    ax.quiver(
        X[mask, 0],
        X[mask, 1],
        X[mask, 2],
        flow[mask, 0],
        flow[mask, 1],
        flow[mask, 2],
        alpha=0.1,
        length=0.5,
    )
    plt.show()


# Cell
# For plotting 2D and 3D graphs
import plotly.express as px
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def plot_3d(
    X,
    distribution=None,
    title="",
    lim=None,
    use_plotly=False,
    colorbar=False,
    cmap="viridis",
):
    if distribution is None:
        distribution = np.zeros(len(X))
    if lim is None:
        lim = np.max(np.linalg.norm(X, axis=1))
    if use_plotly:
        d = {"x": X[:, 0], "y": X[:, 1], "z": X[:, 2], "colors": distribution}
        df = pd.DataFrame(data=d)
        fig = px.scatter_3d(
            df,
            x="x",
            y="y",
            z="z",
            color="colors",
            title=title,
            range_x=[-lim, lim],
            range_y=[-lim, lim],
            range_z=[-lim, lim],
        )
        fig.show()
    else:
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection="3d")
        ax.axes.set_xlim3d(left=-lim, right=lim)
        ax.axes.set_ylim3d(bottom=-lim, top=lim)
        ax.axes.set_zlim3d(bottom=-lim, top=lim)
        im = ax.scatter(X[:, 0], X[:, 1], X[:, 2], c=distribution, cmap=cmap)
        ax.set_title(title)
        if colorbar:
            fig.colorbar(im, ax=ax)
        plt.show()


# Cell
import matplotlib.pyplot as plt
import networkx as nx
from torch_geometric.utils import to_networkx


def visualize_graph(data):
    G = to_networkx(data, to_undirected=False)
    nx.draw_networkx(
        G, pos=nx.spring_layout(G, seed=42), arrowsize=20, node_color="#adade0"
    )
    plt.show()


# Cell
import torch
import matplotlib.pyplot as plt
from torch_geometric.utils import to_dense_adj


def visualize_heatmap(edge_index, order_ind=None):
    dense_adj = to_dense_adj(edge_index)[0]
    if order_ind is not None:
        dense_adj = dense_adj[order_ind, :][:, order_ind]
    plt.imshow(dense_adj, cmap="copper")
    plt.show()
