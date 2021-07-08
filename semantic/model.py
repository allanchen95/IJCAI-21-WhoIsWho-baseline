import sys
from numpy.lib.utils import who
sys.path.append("../")
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
from transformers import BertTokenizer, BertModel
import os
from whole_config import configs
from torch.distributions import Categorical
from torch.autograd import Function
import numpy as np
import logging
# logging.basicConfig(level=logging.INFO)
# logging.getLogger("transformers.tokenization_utils").setLevel(logging.ERROR)


class InfoNCELoss(nn.Module):
    def __init__(self):
        super(InfoNCELoss, self).__init__()
        self.τ = 0.05

    def forward(self, pos_score, neg_score, batch_num, neg_sample):
        # neg_shape = neg_score.size()
        neg_score = neg_score.view(batch_num, neg_sample)

        pos = torch.exp(torch.div(pos_score, self.τ))
        neg = torch.sum(torch.exp(torch.div(neg_score, self.τ)), dim=1).unsqueeze(-1)
        # sum is over positive as well as negative samples
        # print(pos, pos.size())
        # print(neg, neg.size())
        denominator = neg + pos
        # tmp = -torch.log(torch.div(pos,denominator))
        # print(tmp.size(), tmp)
        return torch.mean(-torch.log(torch.div(pos,denominator)))

class bertEmbeddingLayer(nn.Module):
    def __init__(self, bertModel):
        super(bertEmbeddingLayer, self).__init__()
        self.bertModel = bertModel
        # self.args = args


    def forward(self, ins_input_ids, ins_token_type_ids, ins_attention_mask, ins_position_ids, ins_position_ids_second):
        _, pooled_output = self.bertModel.bert.forward(
            input_ids=ins_input_ids,
            token_type_ids=ins_token_type_ids,
            attention_mask=ins_attention_mask,
            output_all_encoded_layers=False,
            checkpoint_activations=False,
            position_ids=ins_position_ids,
            position_ids_second=ins_position_ids_second
        )
        # print(output_embeddings.size())
        # output_encoder = self.Encoder(pooled_output)
        # output_encoder = self.Encoder(last_layer[:,0])

        # exit()
        # sna
        # output_encoder = last_layer[:,0]
        # print(last_layer.size())
        # print(output_encoder.size())
        # exit()
        return _, pooled_output



# class bertEmbeddingLayer(nn.Module):
#     def __init__(self):
#         super(bertEmbeddingLayer, self).__init__()
#         # output_dir = "/home/chenbo/entity_linking/bert_generator/bert-base-multilingual-cased/"
#         output_dir = "/home/chenbo/scibert_scivocab_uncased/"
#         # output_dir = "/home/chenbo/bert-base-uncased/"
#         self.bertModel = BertModel.from_pretrained(output_dir)
#         # self.Encoder = nn.Sequential(
#         #     nn.Linear(configs["hidden_size"], configs["hidden_size"])
#         # )       


#     def forward(self, ins_token_inputs, ins_attention_mask, ins_position_ids = None):
#         outputs = self.bertModel(input_ids = ins_token_inputs, attention_mask = ins_attention_mask)     
#         # outputs:
#             # 1. last_hidden_state: the last layer of the model. (batch_size, sequence_length, hidden_size)
#             # 2. pooler_output: last layer hidden-state of the first token further processed by a Linear layer and a Tanh activation function.(batch_size, hidden_size)
#             # 3. hidden_states: the output of each layer plus the initial embedding outputs. (batch_size, sequence_length, hidden_size)
#         last_layer = outputs[0]
#         pooler_out = outputs[1]
#         # token_embeddings_last_4_layers = torch.cat((outputs[2][-1], outputs[2][-2], outputs[2][-3], outputs[2][-4]), 2) #[batch_size, seqence_len, 4 * 768]
#         # output_encoder = self.Encoder(last_layer[:, 0])
#         # output_encoder = self.Encoder(last_layer)
#         # return pooler_out, token_embeddings_last_4_layers[:, 0], output_encoder
#         # return last_layer, pooler_out, token_embeddings_last_4_layers
#         return last_layer, pooler_out


def kernal_mus(n_kernels):
    """
    get the mu for each guassian kernel. Mu is the middle of each bin
    :param n_kernels: number of kernels (including exact match). first one is exact match
    :return: l_mu, a list of mu.
    """
    l_mu = [1]
    if n_kernels == 1:
        return l_mu

    bin_size = 2.0 / (n_kernels - 1)  # score range from [-1, 1]
    l_mu.append(1 - bin_size / 2)  # mu: middle of the bin
    for i in range(1, n_kernels - 1):
        l_mu.append(l_mu[i] - bin_size)
    print(l_mu)
    return l_mu


def kernel_sigmas(n_kernels):
    """
    get sigmas for each guassian kernel.
    :param n_kernels: number of kernels (including exactmath.)
    :param lamb:
    :param use_exact:
    :return: l_sigma, a list of simga
    """
    bin_size = 2.0 / (n_kernels - 1)
    l_sigma = [0.001]  # for exact match. small variance -> exact match
    if n_kernels == 1:
        return l_sigma

    l_sigma += [0.1] * (n_kernels - 1)
    print(l_sigma)
    return l_sigma

 
class matchingModel(nn.Module):

    def __init__(self, device):
        """
        :param mu: |d| * 1 dimension mu
        :param sigma: |d| * 1 dimension sigma
        """
        super(matchingModel, self).__init__()
        self.n_bins = configs["raw_feature_len"]
        self.device = device
        # print(self.device)
        self.mu = torch.FloatTensor(kernal_mus(self.n_bins)).to(device ,non_blocking=True)
        self.sigma = torch.FloatTensor(kernel_sigmas(self.n_bins)).to(device ,non_blocking=True)

        self.mu = self.mu.view(1, 1, self.n_bins)
        self.sigma = self.sigma.view(1, 1, self.n_bins)
    

    def each_field_model(self, paper_embedding, per_embedding):
        sim_vec = per_embedding @ paper_embedding.transpose(1,0)
        # print(sim_vec)
        sim_vec = sim_vec.unsqueeze(-1)
        # print(sim_vec.size())
        pooling_value = torch.exp((- ((sim_vec - self.mu) ** 2) / (self.sigma ** 2) / 2))
        # print(pooling_value.size())
        pooling_sum = torch.sum(pooling_value, 1)
        # print(pooling_sum.size())
        log_pooling_sum = torch.log(torch.clamp(pooling_sum, min=1e-10)) * 0.01 
        log_pooling_sum = torch.sum(log_pooling_sum, 0)
        # print(log_pooling_sum.size())
        # exit()
        # log_pooling_sum = self.miAttention(log_pooling_sum)
        # print(log_pooling_sum.size())
        return log_pooling_sum


    def get_intersect_matrix(self, paper_embedding, per_embedding):

        sim_vec = self.each_field_model(paper_embedding, per_embedding)
        return sim_vec
        # return log_pooling_sum


    def forward(self, paper_embedding, per_embedding):
        paper_embedding = torch.nn.functional.normalize(paper_embedding, p = 2, dim = 1)
        per_embedding = torch.nn.functional.normalize(per_embedding, p = 2, dim = 1)
        # print(paper_cls_embedding.size(), author_cls_embedding.size(), author_per_cls_embedding.size())
        
        whole_sim = self.get_intersect_matrix(paper_embedding, per_embedding)
        # print(whole_sim.size())
        return whole_sim



class learning2Rank(nn.Module):
    """
    kernel pooling layer
    """

    def __init__(self):
        """
        :param mu: |d| * 1 dimension mu
        :param sigma: |d| * 1 dimension sigma
        """
        super(learning2Rank, self).__init__()
        # self.n_bins = configs["feature_len"] * 2 
        self.learning2Rank = nn.Sequential(
            nn.Linear(configs["feature_len"], configs["feature_len"]),
            nn.Dropout(0.2),
            # F.dropout(0.5, training=self.training),
            nn.LeakyReLU(0.2, True),
            nn.Linear(configs["feature_len"], configs["feature_len"]),
            nn.Dropout(0.2),
            # F.dropout(0.5, training=self.training),
            nn.LeakyReLU(0.2, True),
            nn.Linear(configs["feature_len"], 1),
            # nn.Tanh()
            nn.Sigmoid()
        )

        self.str_vec = strMlp()
        

    def forward(self,whole_sim, str_feature):
        str_feature = str_feature.float()
        whole_sim = whole_sim.float()
        # mi_mf_each_sim = torch.mean(each_sim, dim = 0).unsqueeze(0)
        str2vec = self.str_vec(str_feature.unsqueeze(0))
        total_vec = torch.cat((whole_sim.unsqueeze(0), str2vec), 1)
        print(total_vec.size())
        output = self.learning2Rank(total_vec)
        return output




class ML_learning2Rank(nn.Module):
    def __init__(self):
        super(ML_learning2Rank, self).__init__()
        # self.n_bins = configs["feature_len"] * 2 
        self.learning2Rank = nn.Sequential(
            nn.Linear(configs["str_len"], configs["str_len"]),
            nn.Dropout(0.2),
            # F.dropout(0.5, training=self.training),
            nn.LeakyReLU(0.2, True),
            nn.Linear(configs["str_len"], configs["str_len"]),
            nn.Dropout(0.2),
            # F.dropout(0.5, training=self.training),
            nn.LeakyReLU(0.2, True),
            nn.Linear(configs["str_len"], 1),
            # nn.Tanh()
            nn.Sigmoid()
        )
        self.str_vec = strMlp()
        

    def forward(self, str_feature):

        output = self.learning2Rank(str_feature)
        return output




class DL_learning2Rank(nn.Module):
    def __init__(self):
        super(DL_learning2Rank, self).__init__()
        # self.n_bins = configs["feature_len"] * 2 
        self.learning2Rank = nn.Sequential(
            nn.Linear(configs["dl_len"], configs["dl_len"]),
            nn.Dropout(0.2),
            # F.dropout(0.5, training=self.training),
            nn.LeakyReLU(0.2, True),
            nn.Linear(configs["dl_len"], configs["dl_len"]),
            nn.Dropout(0.2),
            # F.dropout(0.5, training=self.training),
            nn.LeakyReLU(0.2, True),
            nn.Linear(configs["dl_len"], 1),
            # nn.Tanh()
            nn.Sigmoid()
        )

        # self.mf_model = multiField()
        self.mi_model = multiInstance()
        # self.str_vec = strMlp()
        

    def forward(self, whole_sim, each_sim):

        mi_mf_each_sim = self.mi_model(each_sim)

        total_vec = torch.cat((whole_sim, mi_mf_each_sim), 1)

        output = self.learning2Rank(total_vec)

        return output

 
class strMlp(nn.Module):
    def __init__(self):
        super(strMlp, self).__init__()
        self.n_bins = configs["str_len"]
        self.strDenseLayer = nn.Sequential(
            nn.Linear(self.n_bins, self.n_bins),
            nn.Dropout(0.2),
            nn.LeakyReLU(0.2, True),
            nn.Linear(self.n_bins, self.n_bins),
            nn.Dropout(0.2),
            nn.LeakyReLU(0.2, True),
            nn.Linear(self.n_bins, self.n_bins)
        )


    def forward(self, raw_feature):
        print(raw_feature.size())
        str2vec = self.strDenseLayer(raw_feature)

        return str2vec


 
class multiInstance(nn.Module):
    """
    kernel pooling layer
    """
    def __init__(self):
        """
        :param mu: |d| * 1 dimension mu
        :param sigma: |d| * 1 dimension sigma
        """
        super(multiInstance, self).__init__()
        self.n_bins = 22
        # self.miDenseLayer = nn.Sequential(
        #     nn.Linear(self.n_bins, 1)
        # )
        self.miDenseLayer = nn.Sequential(
            nn.Linear(self.n_bins, self.n_bins),
            nn.LeakyReLU(0.2, True),
            nn.Linear(self.n_bins, self.n_bins),
            nn.LeakyReLU(0.2, True),
            nn.Linear(self.n_bins, 1)
        )


    def forward(self, mi_sim_vec):
        mi_attention = self.miDenseLayer(mi_sim_vec)
        # mi_attention = torch.exp(mi_attention.squeeze(-1))
        # # print(mi_attention.size())
        # sumed = torch.sum(mi_attention, dim = 1).unsqueeze(-1)
        # mi_attention = (mi_attention / sumed).unsqueeze(-1)
        # print(mi_attention.size())
        # exit()
        mi_softmax = F.softmax(mi_attention, dim = 0)
        # print(mi_softmax)
        
        # print(mi_sim_vec[:, :6])
        # exit()
        sum_sim_vec = torch.sum(mi_sim_vec * mi_softmax, dim = 0).unsqueeze(0)
        return sum_sim_vec


class multiField(nn.Module):

    def __init__(self):
        """
        :param mu: |d| * 1 dimension mu
        :param sigma: |d| * 1 dimension sigma
        """
        self.n_bins = configs["feature_len"]
        super(multiField, self).__init__()
        self.mfDenseLayer = nn.Sequential(
            nn.Linear(self.n_bins, 1),
            nn.Tanh()
        )
   
    def forward(self, sim_vec1, sim_vec2):
        if(len(sim_vec1.size()) == 1):
            sim_vec1 = sim_vec1.unsqueeze(0)
            sim_vec2 = sim_vec2.unsqueeze(0)
        sim_shape = sim_vec1.size()
        dims = len(sim_shape) - 1
        sim1_att = self.mfDenseLayer(sim_vec1)
        sim2_att = self.mfDenseLayer(sim_vec2)
        attention = torch.cat((sim1_att, sim2_att), dims)
        softmax = F.softmax(attention, dim = dims)
        a1, a2 = torch.split(softmax, 1, dims)
        # print("so: ", softmax.size())
        # print(softmax[:, 0].size())
        merge_vec = sim_vec1 * a1 + sim_vec2 * a2

        return merge_vec