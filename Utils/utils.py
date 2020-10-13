import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
import time

import rdkit.Chem as Chem
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim


# atom idx for ZINC250k, E = empty
ATOM_IDX = {"E": 0, "C": 1, "N": 2, "O": 3, "F": 4, "P": 5, "S": 6, "Cl": 7, "Br": 8, "I": 9}
ATOM_IDX_INV = {0: "E", 1: "C", 2: "N", 3: "O", 4: "F", 5: "P", 6: "S", 7: "Cl", 8: "Br", 9: "I"}
PERIODIC_TABLE = {"C": 6, "N": 7, "O": 8, "F": 9, "P": 15, "S": 16, "Cl": 17, "Br": 35, "I": 53, }
PERIOD_TO_IND = {1: 6, 2: 7, 3: 8, 4: 9, 5: 15, 6: 16, 7: 17, 8: 35, 9: 53}

# bond idx
BOND_IDX = {"ZERO": 0, "SINGLE": 1, "DOUBLE": 2, "TRIPLE": 3}


MAX_NODE = 40
NUM_BOND = len(BOND_IDX)
NUM_ATOM = len(ATOM_IDX)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def generate_adj(mol, is_Tensor=True):
    A = np.zeros([MAX_NODE, MAX_NODE, NUM_BOND])
    A[:, :, 0] = 1

    if mol is not None:
        bonds = [[b.GetBeginAtomIdx(), b.GetEndAtomIdx(), str(b.GetBondType())] for b in mol.GetBonds()]
        for i, j, b_type in bonds:
            A[i, j, :] = 0
            A[j, i, :] = 0
            A[i, j, BOND_IDX[b_type]] = 1
            A[j, i, BOND_IDX[b_type]] = 1

    if not is_Tensor:
        A = np.argmax(A, axis=2)

    return A


def generate_feture(mol):
    X = np.zeros([MAX_NODE, NUM_ATOM])
    if mol is not None:
        atoms = [ATOM_IDX[atom.GetSymbol()] for atom in mol.GetAtoms()]
        for i, a_type in enumerate(atoms):
            X[i, a_type] = 1

        for i in range(MAX_NODE - len(atoms)):
            X[len(atoms)+i, 0] = 1

    return X


def Smiles2Graph(mol, is_Tensor=True):
    Chem.Kekulize(mol, clearAromaticFlags=False)

    A = generate_adj(mol, is_Tensor)
    X = generate_feture(mol)

    return A, X


def DrawMol(mol, out_path, size=(500, 500)):
    drawer = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
    tm = rdMolDraw2D.PrepareMolForDrawing(mol)
    option = drawer.drawOptions()
    option.addAtomIndices = True

    drawer.DrawMolecule(tm)
    drawer.FinishDrawing()

    img = drawer.GetDrawingText()
    with open(out_path, mode="wb") as f:
        f.write(img)


def orderBFSmol(A, X, num_atom):
    rwmol = Chem.RWMol()

    bfs_queue = [0]
    visited_node = []
    new_index = [-1 for i in range(A.shape[0])]

    rwmol.AddAtom(Chem.Atom(PERIOD_TO_IND[int(np.argmax(X[0:]))]))
    new_index[0] = 0
    ind_counter = 1

    while len(bfs_queue) > 0:
        c_node = bfs_queue[0]
        bfs_queue = bfs_queue[1:]

        for i in range(num_atom):
            btype = A[c_node, i]
            if btype != 0 and i not in visited_node and i not in bfs_queue:
                bfs_queue.append(i)
                rwmol.AddAtom(Chem.Atom(PERIOD_TO_IND[int(np.argmax(X[i:]))]))
                new_index[i] = ind_counter
                ind_counter += 1

        for i in visited_node:
            btype = A[c_node, i]
            if btype == 1:
                rwmol.AddBond(new_index[c_node], new_index[i], Chem.BondType.SINGLE)
            elif btype == 2:
                rwmol.AddBond(new_index[c_node], new_index[i], Chem.BondType.DOUBLE)
            elif btype == 3:
                rwmol.AddBond(new_index[c_node], new_index[i], Chem.BondType.TRIPLE)
        visited_node.append(c_node)

    mol = rwmol.GetMol()
    # Chem.SanitizeMol(mol)

    return mol


def read_smilesset(path):
    smiles_list = []
    with open(path) as f:
        for smiles in f:
            smiles_list.append(smiles.rstrip())

    return smiles_list


