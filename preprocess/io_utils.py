# -*- coding: utf-8 -*-
import numpy as np
import sys
from random import shuffle

def naive_seg(sentence):
    ''' Seqment the sentence into words seperated by space
        Return segment list
        Input sentence should be utf-8 encoding
        e.g.
            你的English真的是very good的呢
            ->[你,的,English,真,的,是,very,good,的,呢]
    '''
    #sentence = sentence.decode('utf-8')
    try:
        sentence = sentence.decode('utf-8')
    except UnicodeError:
        pass
    sentence = sentence.split()
    sentence_seg = []
    for w in sentence:
        tmp_w = ''
        for c in w:
            if u'\u4e00' <= c <= u'\u9fff':
                if len(tmp_w) > 0:
                    sentence_seg.append(tmp_w)
                sentence_seg.append(c)
                tmp_w = ''
            else:
                tmp_w += c
        if len(tmp_w) > 0:
            sentence_seg.append(tmp_w)
    return sentence_seg


def load_X(X_path):
    '''Load _X file
    '''
    X = []
    with open(X_path,'r') as f:
        for line in f:
            line = line.decode('utf-8')
            X.append(line.split())
    return X

def load_POS(pos_path):
    '''Load _POS file
    '''
    return load_X(pos_path)

def load_Intent(Intent_path):
    '''Load _Intent file
    '''
    Intent = []
    with open(Intent_path,'r') as f:
        for line in f:
            line = line.decode('utf-8')
            Intent.append(line.rstrip())
    return Intent

def dump_to_file(X,POS,Intent,prefix, mode='w'):
    f_X = open(prefix+'X',mode)
    f_POS = open(prefix+'POS',mode)
    f_Intent = open(prefix+'Intent',mode)

    for n in range(len(X)):
        for i in X[n]:
            f_X.write(u'{} '.format(i).encode('utf-8'))
        f_X.write(u'\n'.encode('utf-8'))
        for i in POS[n]:
            f_POS.write(u'{} '.format(i).encode('utf-8'))
        f_POS.write(u'\n'.encode('utf-8'))
        f_Intent.write(u'{}\n'.format(Intent[n]).encode('utf-8'))
    f_X.close()
    f_POS.close()
    f_Intent.close()

def shuffle_data(prefix):
    with open(prefix+'X','r')  as f:
        X = f.read().splitlines()
    with open(prefix+'POS','r') as f:
        POS = f.read().splitlines()
    with open(prefix+'Intent','r') as f:
        Intent = f.read().splitlines()
    
    X = [a.decode('utf-8') for a in X]
    X_shuf = []
    POS_shuf = []
    Intent_shuf = []
    index_shuf = range(len(X))
    shuffle(index_shuf)
    for i in index_shuf:
        X_shuf.append(X[i])
        POS_shuf.append(POS[i])
        Intent_shuf.append(Intent[i])

    f_X = open(prefix+'X', 'w')
    f_POS = open(prefix+'POS', 'w')
    f_Intent = open(prefix+'Intent', 'w')

    for n in range(len(X_shuf)):
        for i in X_shuf[n]:
            f_X.write(u'{}'.format(i).encode('utf-8'))
        f_X.write(u'\n'.encode('utf-8'))
        for i in POS_shuf[n]:
            f_POS.write(u'{}'.format(i).encode('utf-8'))
        f_POS.write(u'\n'.encode('utf-8'))
        f_Intent.write(u'{}\n'.format(Intent_shuf[n]).encode('utf-8'))
    f_X.close()
    f_POS.close()
    f_Intent.close()



if __name__ == '__main__':
    naive_seg('我想聽[s]的')
