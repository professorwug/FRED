# AUTOGENERATED! DO NOT EDIT! File to edit: 03e Investigations in directed diffusion.ipynb (unless otherwise specified).

__all__ = ['ManifoldFlowEmbedder', 'auto_encoder', 'flow_artist', 'GaussianVectorField', 'precomputed_distance_loss',
           'flow_neighbor_loss', 'anisotropic_kernel', 'smoothness_of_vector_field', 'kl_divergence_loss',
           'FlowPredictionDataset', 'FlowPredictionEmbedder', 'compute_grid', 'diffusion_matrix_with_grid_points',
           'flow_gif']

# Cell
import torch
import torch.nn as nn
from .data_processing import affinity_matrix_from_pointset_to_pointset


class ManifoldFlowEmbedder(torch.nn.Module):
    def __init__(
        self,
        embedding_dimension=2,
        embedder_shape=[3, 4, 8, 4, 2],
        device=torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        sigma=0.5,
        flow_strength=0.5,
        smoothness_grid=True,
    ):
        super().__init__()
        self.device = device
        self.embedding_dimension = embedding_dimension
        # embedding parameters
        self.sigma = sigma
        self.flow_strength = flow_strength
        self.smoothness_grid = smoothness_grid
        # Initialize autoencoder and flow artist
        self.embedder, self.decoder = auto_encoder(embedder_shape, device=self.device)
        self.flowArtist = flow_artist(dim=self.embedding_dimension, device=self.device)
        # training ops
        self.KLD = nn.KLDivLoss(reduction="batchmean", log_target=False)
        self.MSE = nn.MSELoss()
        # self.KLD = homemade_KLD # when running on mac
        self.epsilon = 1e-6  # set zeros to eps

    def loss(self, data, loss_weights):
        # compute autoencoder loss
        losses = {}
        if loss_weights["reconstruction"] != 0:
            X_reconstructed = self.decoder(self.embedded_points)
            losses["reconstruction"] = self.MSE(X_reconstructed, data["X"])
        # Compute diffusion map loss
        if loss_weights["diffusion map regularization"] != 0:
            diffmap_loss = precomputed_distance_loss(
                data["precomputed distances"], self.embedded_points
            )
            #           diffmap_loss = diffusion_map_loss(self.P_graph_ts[0], self.embedded_points)
            losses["diffusion map regularization"] = diffmap_loss

        # Compute flow neighbor loss
        if loss_weights["flow neighbor loss"] != 0:
            neighbor_loss = flow_neighbor_loss(
                data["neighbors"],
                self.embedded_points,
                self.embedded_flows,
            )
            losses["flow neighbor loss"] = neighbor_loss

        # Compute smoothness regularization
        if loss_weights["smoothness"] != 0:
            smoothness_loss = smoothness_of_vector_field(
                self.embedded_points,
                self.flowArtist,
                device=self.device,
                grid_width=20,
                use_grid=self.smoothness_grid,
            )
            losses["smoothness"] = smoothness_loss

        if loss_weights["kld"] != 0:
            A = affinity_matrix_from_pointset_to_pointset(self.embedded_points, self.embedded_points, self.embedded_flows, sigma=0.5, flow_strength=1)
            P = torch.nn.functional.normalize(A, p=1, dim=1)
            losses['kld'] = kl_divergence_loss(P, data["P"])
        return losses

    def forward(self, data, loss_weights):
        self.embedded_points = self.embedder(data["X"])
        self.embedded_flows = self.flowArtist(self.embedded_points)
        losses = self.loss(data, loss_weights)
        return losses

# Cell

import torch
import torch.nn as nn
from collections import OrderedDict

def auto_encoder(enc_shape, device = torch.device('cpu')):

    # Function to create tailored encoder

    # todo, maybe? create autoencoder only given input and output dimensions
    """
    if input_dim > output_dim:
        raise Exception("Output dimension is greater than input dimension. Why embed? Mu.")
    """

    enc = nn.Sequential()

    d_len = len(enc_shape)*2
    d = OrderedDict()
    d[str(0)] = nn.Linear(enc_shape[0], enc_shape[1])
    for i in range(1,d_len-3):
        if i%2 == 1:
            d[str(i)] = nn.LeakyReLU()
        else:
            d[str(i)] = nn.Linear(enc_shape[int(i/2)], enc_shape[int(i/2)+1])

    # create MLP
    enc = nn.Sequential(d).to(device) # d is an OrderedDictionary

    # decoder start

    enc_shape.reverse()
    dec_shape = enc_shape
    dec = nn.Sequential()

    d_len = len(dec_shape)*2
    d = OrderedDict()
    d[str(0)] = nn.Linear(dec_shape[0], dec_shape[1])
    for i in range(1,d_len-3):
        if i%2 == 1:
            d[str(i)] = nn.LeakyReLU()
        else:
            d[str(i)] = nn.Linear(dec_shape[int(i/2)], dec_shape[int(i/2)+1])

    # create MLP
    dec = nn.Sequential(d).to(device) # d is an OrderedDictionary

    return enc, dec

# Cell

import torch
import torch.nn as nn
from collections import OrderedDict

def flow_artist(dim = 2, device = torch.device('cpu')):
    # Function to create tailored flow artist

    shape = [dim,dim*2,dim*4,dim*4,dim*2,dim]

    FA = nn.Sequential()

    d_len = len(shape)*2
    d = OrderedDict()
    d[str(0)] = nn.Linear(shape[0], shape[1])
    for i in range(1,d_len-3):
        if i%2 == 1:
            d[str(i)] = nn.LeakyReLU()
        else:
            d[str(i)] = nn.Linear(shape[int(i/2)], shape[int(i/2)+1])

    # create MLP
    FA = nn.Sequential(d).to(device) # d is an OrderedDictionary

    return FA

# Cell
import torch.nn as nn
class GaussianVectorField(nn.Module):
  def __init__(self,n_dims, n_gaussians, device, random_initalization = True):
    super(GaussianVectorField, self).__init__()
    self.n_dims = n_dims
    # each gaussian has a mean and a variance, which are initialized randomly, but
    # are afterwards tuned by the network
    self.means = torch.nn.Parameter(torch.rand(n_gaussians,n_dims)*8 - 4).to(device)
    if random_initalization:
      vecs = torch.randn(n_gaussians,n_dims)
    else:
      vecs = torch.ones(n_gaussians,n_dims)
    vecs = vecs / torch.linalg.norm(vecs, dim=1)[:,None]
    self.vectors = torch.nn.Parameter(vecs).to(device)
  def forward(self,points):
    # evaluates the vector field at each point
    # First, take distances between the points and the means
    dist_between_pts_and_means = torch.cdist(points,self.means)
    # print("distances between points and means",dist_between_pts_and_means)
    # apply kernel to this
    # creates n_points x n_means array
    kernel_from_mean = torch.exp(-(dist_between_pts_and_means**2))
    # print("kernalized",kernel_from_mean)
    # multiply kernel value by vectors associated with each Gaussian
    kernel_repeated = kernel_from_mean[:,:,None].repeat(1,1,self.n_dims)
    # print('kernel repeated has shape',kernel_repeated.shape, 'and vecs has shape', self.vectors.shape)
    kernel_times_vectors = kernel_repeated * self.vectors
    # creates tensor of shape
    # n_points x n_means x n_dims
    # collapse along dim 1 to sum vectors along dimension
    vector_field = kernel_times_vectors.sum(dim=1)
    return vector_field

# Cell
import torch
def precomputed_distance_loss(precomputed_distances, embedded_points):
    D_graph = precomputed_distances
    num_nodes = embedded_points.shape[0]
    D_embedding = torch.cdist(embedded_points, embedded_points)
    loss = torch.norm(D_graph - D_embedding)**2 / (num_nodes**2)
    return loss

# Cell
def flow_neighbor_loss(neighbors, embedded_points, embedded_flows):
  row, col = neighbors
  directions = (embedded_points[col] - embedded_points[row])
  flows = embedded_flows[row]
  loss = torch.norm(directions - flows)**2
  return loss

# Cell
def anisotropic_kernel(D, sigma=0.7, alpha = 1):
  """Computes anisotropic kernel of given distances matrix.

  Parameters
  ----------
  D : ndarray or sparse
  sigma : float, optional
      Kernel bandwidth, by default 0.7
  alpha : int, optional
      Degree of density normalization, from 0 to 1; by default 1
  This is a good function.
  """
  W = torch.exp(-D**2/(2*sigma**2))
  # Additional normalization step for density
  D = torch.diag(1/(torch.sum(W,axis=1)**alpha))
  W = D @ W @ D
  return W

# Cell
def smoothness_of_vector_field(embedded_points, vector_field_function, device, use_grid = True, grid_width = 20):
    if use_grid:
        # find support of points
        minx = (min(embedded_points[:,0])-1).detach()
        maxx = (max(embedded_points[:,0])+1).detach()
        miny = (min(embedded_points[:,1])-1).detach()
        maxy = (max(embedded_points[:,1])+1).detach()
        # form grid around points
        x, y = torch.meshgrid(torch.linspace(minx,maxx,steps=grid_width),torch.linspace(miny,maxy,steps=grid_width))
        xy_t = torch.concat([x[:,:,None],y[:,:,None]],dim=2).float()
        xy_t = xy_t.reshape(grid_width**2,2).to(device)
        points_to_test = xy_t
    else:
        points_to_test = embedded_points
    # Compute distances between points
    # TODO: Can compute A analytically for grid graph, don't need to run kernel
    Dists = torch.cdist(points_to_test,points_to_test)
    A = anisotropic_kernel(Dists)
    # Get degree matrix and build graph laplacian
    D = A.sum(axis=1)
    L = torch.diag(D) - A
    # compute vector field at each grid point
    vecs = vector_field_function(points_to_test)
    x_vecs = vecs[:,0]
    y_vecs = vecs[:,1]
    # compute smoothness of each x and y and add them # TODO: There are other ways this could be done
    x_smoothness = (x_vecs.T @ L @ x_vecs) / torch.max(torch.linalg.norm(x_vecs)**2, torch.tensor(1e-5))
    y_smoothness = (y_vecs.T @ L @ y_vecs) / torch.max(torch.linalg.norm(y_vecs)**2, torch.tensor(1e-5))
    total_smoothness = x_smoothness + y_smoothness
    return total_smoothness

# Cell
def kl_divergence_loss(P_embedding, P_graph):
    P_embedding = torch.log(P_embedding)
    if P_embedding.is_sparse:
        P_embedding = P_embedding.to_dense()
        P_graph = P_graph.to_dense()
    loss = torch.nn.functional.kl_div(P_embedding, P_graph, reduction='batchmean')
    # print("kld loss",loss)
    return loss

# Cell
import torch
from torch.utils.data import Dataset
import matplotlib.pyplot as plt
import numpy as np
import torch.nn.functional as F
from tqdm.notebook import trange, tqdm
from .data_processing import flashlight_affinity_matrix, diffusion_map_from_affinities, flow_neighbors
class FlowPredictionDataset(Dataset):
    """
    Dataset object to be used with FRED for pointcloud and velocity input data.
    Takes np.arrays for X (points) and velocities (velocity vectors per point).
    For each item retrieved, returns a neighborhood around that point (based on local euclidean neighbors) containing local affinities

    """
    def __init__(self,
                X,
                velocities,
                labels,
                sigma="automatic",
                ts = (1,2,4,8),
                prior_embedding = "diffusion map",
                t_dmap = 1,
                dmap_coords_to_use = 2,):
        # Step 0: Convert data into tensors
        self.X = torch.tensor(X).float()
        self.velocities = torch.tensor(velocities).float()
        self.labels = labels
        self.n_nodes = self.X.shape[0]
        self.eps = 1e-3
        # Step 1. Build graph on input data, using flashlight kernel
        print("finding diffusion operator")
        self.A = flashlight_affinity_matrix(self.X, self.velocities, sigma = sigma)
        self.A[self.A < self.eps] = 0
        # visualize affinity matrix
        plt.imshow(self.A.numpy())
        # Construct diffusion matrix as row normalized adjacency matrix
        self.P_graph = F.normalize(self.A, p=1, dim=1)
        # threshold values less than epsilon to zero
        # We convert P_graph into sparse format to efficiently power
        self.P_graph = self.P_graph.to_sparse().coalesce()
        # Compute powers of P (really fast, because it's sparse : )
        self.P_graph_ts = [self.P_graph]
        print("Powering diffusion operator")
        for t in tqdm(ts[1:]):
            # TODO Can make more efficient by using prior powers
            powered_matrix = torch.linalg.matrix_power(self.P_graph_ts[0], t).coalesce()
            dense_powered = powered_matrix.to_dense()
            dense_powered[dense_powered < self.eps] = 0
            sparse_powered = dense_powered.to_sparse()
            self.P_graph_ts.append(sparse_powered)
            # TODO: Could proactively prune probs below eps threshold here.


        # Step 2. Take a diffusion map of the data
        # These will become our 'precomputed distances' which we use to regularize the embedding
        if prior_embedding == "diffusion map":
            print("computing diffusion distances")
            P_dense = self.P_graph.clone().to_dense()
            P_graph_symmetrized = P_dense + P_dense.T
            diff_map = diffusion_map_from_affinities(
                # TODO: May need to convert back to dense form.
                P_graph_symmetrized, t=t_dmap, plot_evals=False
            )
            self.diff_coords = diff_map[:, :dmap_coords_to_use]
            self.diff_coords = self.diff_coords.real
            self.diff_coords = torch.tensor(self.diff_coords.copy()).float()
            self.precomputed_distances = torch.cdist(self.diff_coords, self.diff_coords)
            # scale distances between 0 and 1
            self.precomputed_distances = 2 * (
                self.precomputed_distances / torch.max(self.precomputed_distances)
            )
            self.precomputed_distances = (
                self.precomputed_distances.detach()
            )  # no need to have gradients from this operation

        # Step 3. Decompose the affinity matrix into a list of indices [i,j], which we use to form batches
        # To prevent this from making the batch have size n x n, we use the *nonzero* indices of the
        # sparse powered diffusion matrices.
        # But each powered diffusion matrix will have different nonzero values. Hence, we want the union of all relationships which
        # at some level of diffusion, are nonzero
        # print("sparse Pts are",self.P_graph_ts)
        all_P_values = self.P_graph_ts[0]
        for i in range(1,len(ts)):
            # print(i)
            all_P_values += all_P_values + self.P_graph_ts[i]
            all_P_values = all_P_values.coalesce()
        self.diffusion_indices = all_P_values.indices()
        # returns matrix whose columns are indices
        # tensor([[0, 1, 1],
        #         [2, 0, 2]])
        # convert to matrix whose rows are indices
        self.diffusion_indices = self.diffusion_indices.transpose(0,1)
    def __len__(self):
        return len(self.diffusion_indices)
    def __getitem__(self, idx):
        # idx specifies the ith tuple of points in the diffusion indices.
        happy_couple = self.diffusion_indices[idx]
        # print("hc is",happy_couple)
        # Construct diffusion probabilities into a list of tensors
        probs = torch.zeros(len(self.P_graph_ts))
        transition_to = torch.zeros(len(self.P_graph_ts))
        for i, Pt in enumerate(self.P_graph_ts):
            probs[i] = Pt[happy_couple[0]][happy_couple[1]]
            transition_to[i] = (probs[i] > 0.5).to(int)
        # print("got Pt probs just fine")
        # print("first sum worked")
        # Fetch points from X
        points = self.X[happy_couple]
        # print("got points just fine")
        # Embed these into a dictionary for easy cross reference
        return_dict = {
            "idxs":happy_couple,
            "probs":probs,
            "transition_to": transition_to,
            "distance":self.precomputed_distances[happy_couple[0]][happy_couple[1]],
            "X":points,
        }
        return return_dict

# Cell
import torch
import torch.nn as nn
from .data_processing import affinity_matrix_from_pointset_to_pointset

class FlowPredictionEmbedder(torch.nn.Module):
    def __init__(
        self,
        embedding_dimension=2,
        ts = [1,2,4,8],
        embedder_shape=[3, 4, 8, 4, 2],
        device=torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        sigma=0.5,
        flow_strength=0.5,
        smoothness_grid=True,
    ):
        super().__init__()
        self.device = device
        self.embedding_dimension = embedding_dimension
        # embedding parameters
        self.sigma = sigma
        self.flow_strength = flow_strength
        self.smoothness_grid = smoothness_grid
        self.ts = ts
        self.t_weights = [1,0.5,0.25,0.125]
        # Initialize autoencoder and flow artist

        # self.embedder, self.decoder = auto_encoder(embedder_shape, device=self.device)
        self.embedder = fixed_diffmap_embedder
        self.flowArtist = flow_artist(dim=self.embedding_dimension, device=self.device)
        # # training ops
        # self.KLD = nn.KLDivLoss(reduction="batchmean", log_target=False)
        self.MSE = nn.MSELoss()
        # self.KLD = homemade_KLD # when running on mac
        self.epsilon = 1e-6  # set zeros to eps
        # self.log_softmax = nn.LogSoftmax()
        self.loss = nn.BCELoss()

    def diffusion_flow_probs(self):
        # Predict flow probabilities to points based on a local diffusion matrix, constructed out of the batch
        # Penalize by cross entropy against expected probabilities
        # We use the embedded points and our FlowArtist to predict diffusion probabilities
        # Steps:
        # 1. Build diffusion matrix (using automatic kernel selection with flashlight kernel)
        A = affinity_matrix_from_pointset_to_pointset(self.embedded_points, self.embedded_points, self.embedded_flows, sigma=0.5, flow_strength=1)
        P = F.normalize(A, p=1, dim=1)
        # 2. Power diffusion matrix
        self.Pts = [torch.linalg.matrix_power(P,t) for t in self.ts]
        # 3. Convert from powered pointwise probs to the probs between pairs of points, in the format originally given.
        diffusion_probs = []
        for Pt in self.Pts:
            diffusion_probs.append(
                Pt.diagonal(offset = 1)[torch.arange(len(self.embedded_points)//2)*2]
            )
        return diffusion_probs

    def forward(self, data, loss_weights):
        # Extract data from batch
        # By default, point positions are batched two at a time.
        # We need to flatten along the second dimension
        # # print data shapes
        # for k in data.keys():
        #     print(f"{k} shape {data[k].shape}")
        X = data["X"].flatten(start_dim=0, end_dim=1)
        embedding_idxs = data['idxs'].flatten()
        self.embedded_points = self.embedder(X, embedding_idxs)
        self.embedded_flows = self.flowArtist(self.embedded_points)
        # Compute Losses
        losses = {}
        # Compute predicted diffusion flow probabilities
        diffusion_probs = self.diffusion_flow_probs()
        y = data["transition_to"]
        # Loop through each t and compute a weighted multiscale loss
        cost = 0
        for i, t in enumerate(self.ts):
            cost += self.loss(diffusion_probs[i],y[:,i]) * self.t_weights[i]
        # print("predicted ",diffusion_probs[0])
        # print("actually ", y[:,0])
        losses["flow prediction"] = cost

        # Get autoencoder loss
        # X_reconstructed = self.decoder(self.embedded_points)
        # losses["reconstruction"] = self.MSE(X_reconstructed, X)
        return losses

# Cell
from .data_processing import (
    affinity_matrix_from_pointset_to_pointset
)
def compute_grid(X, grid_width=20):
    """Returns a grid of points which bounds the points X.
    The grid has 'grid_width' dots in both length and width.
    Accepts X, tensor of shape n x 2
    Returns tensor of shape grid_width^2 x 2"""
    # TODO: This currently only supports
    # find support of points
    minx = float(torch.min(X[:, 0]) - 0.1)  # TODO: use torch.min, try without detach
    maxx = float(torch.max(X[:, 0]) + 0.1)
    miny = float(torch.min(X[:, 1]) - 0.1)
    maxy = float(torch.max(X[:, 1]) + 0.1)
    # form grid around points
    x, y = torch.meshgrid(
        torch.linspace(minx, maxx, steps=grid_width),
        torch.linspace(miny, maxy, steps=grid_width),
        indexing="ij",
    )
    xy_t = torch.concat([x[:, :, None], y[:, :, None]], dim=2).float()
    xy_t = xy_t.reshape(grid_width**2, 2).detach()
    return xy_t

# Cell
import torch
from .data_processing import (
    affinity_matrix_from_pointset_to_pointset,
)
import torch.nn.functional as F

def diffusion_matrix_with_grid_points(X, grid, flow_function, t, sigma, flow_strength):
    n_points = X.shape[0]
    # combine the points and the grid
    points_and_grid = torch.concat([X, grid], dim=0)
    # get flows at each point
    flow_per_point = flow_function(points_and_grid)
    # take a diffusion matrix
    A = affinity_matrix_from_pointset_to_pointset(
        points_and_grid,
        points_and_grid,
        flow=flow_per_point,
        sigma=sigma,
        flow_strength=flow_strength,
    )
    P = F.normalize(A, p=1, dim=-1)
    # TODO: Should we remove self affinities? Probably not, as lazy random walks are advantageous when powering
    # Power the matrix to t steps
    Pt = torch.matrix_power(P, t)
    # Recover the transition probabilities between the points, and renormalize them
    Pt_points = Pt[:n_points, :n_points]
    # Pt_points = torch.diag(1/Pt_points.sum(1)) @ Pt_points
    Pt_points = F.normalize(Pt_points, p=1, dim=1)
    # return diffusion probs between points
    return Pt_points

# Cell
from .datasets import plot_directed_2d, plot_directed_3d
import glob
import base64
import ipywidgets as widgets
import os
from tqdm.notebook import tqdm
from PIL import Image
import datetime

def flow_gif(X, flows, P, dataset_name, max_t = 128, plot_3d = False, duration = 40):
    """Creates gif showing the t step diffusion probabilities under evolving time.
    """
    timestamp = datetime.datetime.now().isoformat()
    save_path = f"visualizations/{dataset_name}_diffusions_{timestamp}"
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    ts = [n for n in range(max_t)]
    for i, t in tqdm(enumerate(ts)):
        Pt = torch.linalg.matrix_power(P, t)
        title = f"{save_path}/t{i:03d}"
        if plot_3d:
            plot_directed_3d(X, flows, labels = Pt[0], save=True, filename=title, mask_prob=0)
        else:
            plot_directed_2d(X, flows, labels = Pt[0], save=True, filename=title, mask_prob=0)
    # Make gif of diffusions
    file_names = glob.glob(f"{save_path}/t*.png")
    file_names.sort()
    frames = [Image.open(image) for image in file_names]
    frame_one = frames[0]
    frame_one.save(
        f"{save_path}/_compiled.gif",
        format="GIF",
        append_images=frames,
        save_all=True,
        duration=duration,
        loop=0,
    )
    # display in jupyter notebook
    b64 = base64.b64encode(
        open(f"{save_path}/_compiled.gif", "rb").read()
    ).decode("ascii")
    display(widgets.HTML(f'<img src="data:image/gif;base64,{b64}" />'))
