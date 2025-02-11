# -*- coding: utf-8 -*-
from __future__ import print_function
import numpy as np
import pandas as pd
import argparse
import json
import sys
import re
import string
import random

from utils import io_utils
from random import randrange, shuffle
from os.path import join


intents = ['search', 'recommend', 'info', 'neutral']
slots = ['artist','track', 'genre']
tokens = ['[s]','[t]','[g]']
slot_token_map = {'artist':'[s]', 'track':'[t]', 'genre':'[g]'}
token_slot_map = {'[s]':'artist', '[t]':'track', '[g]':'genre'}
SUCCESS_REWARD = 10.
TURN_REWARD = -0.1

def opt_parse():
    parser = argparse.ArgumentParser(description=\
            'Slot & intent data generate')
    parser.add_argument('--template_dir',default='./data/template/',\
            help='sentence template directory')
    parser.add_argument('--data',default='./data/chinese_artist.json',\
            help='artist-album-track json data')
    parser.add_argument('--genre',default='./data/genres.json',\
            help='genres')
    parser.add_argument('--genre_map',default='./data/genre_map.json',\
            type=str,help='genre_map.json path')
    parser.add_argument('--nlu_data', default='./data/nlu_data/',type=str, help='data dir')
    parser.add_argument('--model',default='./model_tmp/',type=str,help='model dir')
    parser.add_argument('--mode',default='test_dst', type=str, help='stdin|test_dst')
    parser.add_argument('-v',dest='verbose',default=False,action='store_true',help='verbose')
    args = parser.parse_args()
    return args

class Simulator():
    def __init__(self, template_dir, data_path, genre_path, genre_map_path, intents=intents):
        self.data = self.__load_data(template_dir, data_path, genre_path, genre_map_path)
        self.intents = intents[:3]
        self.prefix_pos_responses = [u'是的',u'對', u'恩',u'對阿',u'沒錯', u'是']
        self.prefix_neg_responses = [u'不是 ',u'錯了 ', u'不對 ']

        self.dialogue_end = True
        self.cur_set_goal = False
        self.cur_intent = ''
        self.cur_slot = {}
        self.cur_nb_turn = -1 # simulator started by receive an init question
        self.cur_reward = 0. # cumulated reward
        self.cur_success = False
        self.cur_slots_all = set()

    def set_user_goal(self, intent=None, artist=None, track=None, genre=None, random_init=False):
        ''' set the current user goal. manually init each slot or random_init
        '''
        self.__reset_cur()

        self.cur_intent = intent
        self.cur_slot['artist'] = artist
        self.cur_slot['track'] = track
        self.cur_slot['genre'] = None
        if self.cur_intent == 'recommend': # only recommend would have genre slot
            self.cur_slot['genre'] = genre

        ### if random init
        if random_init:
            # remove punctuation
            #regex = re.compile('[%s]' % re.escape(string.punctuation))
            self.cur_intent = self.__rand(self.intents)
            self.cur_slot['track'] = self.__rand(self.data['tracks'])
            self.cur_slot['artist'] =  self.data['track_artist_map'][self.cur_slot['track']]
            ### TODO: random init genre as well
            if self.cur_intent == 'recommend':
                self.cur_slot['genre'] = self.__rand(self.data['genres'])
            if self.cur_intent == 'info':
                if random.random() > 0.5:
                    self.cur_slot['track'] = None
                else:
                    self.cur_slot['artist'] = None

        ### all the possible slots set based on current intent
        self.cur_slots_all = set([s for s in self.cur_slot if self.cur_slot[s] is not None]) 
        self.cur_templates = self.data['intent_template_map'][self.cur_intent] # use the current intent template
        self.cur_set_goal = True

    def user_response(self, dst_msg=None, start=False):
        ''' Given DST message, return user response
            Arguments:
                dst_msg: DST message. {'action':'confirm|question|response|info',\
                            'intent':'', 'slot':{'slot_name':'value'}}
                start: user start the conversation(equal to get dst_msg{'action':'question'})
            Return:
                sent: string, user response
        '''
        # if user start the conversation
        if start:
            dst_msg = {'action':'question'}

        ### init
        self.dialogue_end = False
        self.cur_nb_turn += 1
        sent=''
        slots_asked = set([])
        intent_asked = ''
        if 'slot' in dst_msg: # init slots asked
            for key in dst_msg['slot']:
                slots_asked.add(key)
        if 'intent' in dst_msg: # init intent_asked
            intent_asked = dst_msg['intent']

        if dst_msg is None and not self.dialogue_end:
            ### NOTE: should not happen
            print ('[ERROR] Need DST message...')
        
        if dst_msg['action'] == 'confirm':
            sent = self.__confirm(dst_msg, slots_asked, intent_asked)
        elif dst_msg['action'] == 'question':
            sent = self.__question(dst_msg, slots_asked, intent_asked)
        elif dst_msg['action'] == 'response':
            self.dialogue_end = True
        elif dst_msg['action'] == 'info':
            self.dialogue_end = True
        
        ### return reward
        if self.dialogue_end:
            self.__reward_calculate(dst_msg)
            
        return sent

    def sentence_generate(self, slots_asked=set([]), strict=True):
        '''strict: use the template contain all the slots_asked
        '''
        #intent_asked = intent_asked if len(intent_asked) > 0 else self.cur_intent
        shuffle(self.cur_templates)
        slots_all = set(slots)
        for t in self.cur_templates:
            t = t.decode('utf-8')
            ### if no slots asked, use the any template which contains any currrent slot and 
            ### doesn't contain any other slots
            if len(slots_asked) is 0 and any(slot_token_map[s] in t for s in self.cur_slots_all)\
                    and all(slot_token_map[s] not in t for s in slots_all - self.cur_slots_all):
                sent = self.__fill_slot(t)
                break
            ### else if the template contains the slot asked and doesn't contain any other slots
            if strict:
                if all(slot_token_map[s] in t for s in slots_asked) and\
                        all(slot_token_map[s] not in t for s in slots_all - slots_asked):
                    sent = self.__fill_slot(t)
                    break
            else:
                if any(slot_token_map[s] in t for s in slots_asked) and\
                        all(slot_token_map[s] not in t for s in slots_all - slots_asked):
                    sent = self.__fill_slot(t)
                    break
        return sent


    def get_reward(self):
        ''' Return current reward
            can only be called after user_response()
        '''
        value = TURN_REWARD
        if self.cur_success:
            value += SUCCESS_REWARD
        return value

    def __fill_slot(self, template):
        #new_temp = io_utils.naive_seg(template)
        self.cur_state['intent'] = self.cur_intent # For DST state accuracy computing
        new_temp = template
        for key in tokens:
            if key in new_temp:
                #offset = new_temp.index(key)
                offset = new_temp.find(key)
                #slot_content = io_utils.naive_seg(self.cur_slot[token_slot_map[key]])
                slot_content= self.cur_slot[token_slot_map[key]]
                new_temp = new_temp[:offset] + slot_content + new_temp[offset+3:]

                # For dst cur state accuracy computing
                self.cur_state['slot'][token_slot_map[key]] = self.cur_slot[token_slot_map[key]]

        return new_temp


    def print_cur_user_goal(self):
        # NOTE Debug
        print (u'[DEBUG] intent:[{}], artist:[{}], track:[{}],genre:[{}], reward:[{}], turns:[{}], success:[{}]'.\
                format(self.cur_intent, self.cur_slot['artist'],\
                self.cur_slot['track'], self.cur_slot['genre'],\
                self.cur_reward, self.cur_nb_turn, self.cur_success))


    def dst_cur_state_check(self, dst_confirmed_state):
        ''' Check if DST current state is correct'''
        print(dst_confirmed_state)
        for key in self.cur_slot:
            if type(dst_confirmed_state['slot'][key]) is float:
                dst_confirmed_state['slot'][key] = None
            if dst_confirmed_state['slot'][key] is not None:
                dst_confirmed_state['slot'][key] = dst_confirmed_state['slot'][key].replace(' ','')
            if self.cur_state['slot'][key] is not None:
                self.cur_state['slot'][key] = self.cur_state['slot'][key].replace(' ','')

        ### check for each slot and intent if all correct
        if dst_confirmed_state['intent'] == self.cur_state['intent'] and\
            dst_confirmed_state['slot']['artist'] == self.cur_state['slot']['artist'] and\
            dst_confirmed_state['slot']['track'] == self.cur_state['slot']['track'] and\
            dst_confirmed_state['slot']['genre'] == self.cur_state['slot']['genre']:
                return True


    def __confirm(self, dst_msg, slots_asked, intent_asked):
        sent = ''
        if 'slot' in dst_msg:
            if not self.cur_slots_all >= slots_asked: # if DTW ask slots not included in current intent
                sent = self.__neg_response(None)
            else:
                slots_asked.clear() # clear all the elements
                for key in dst_msg['slot']: # check if each slot DTW returned is correct
                    ### add incorrect slots to slots_asked, then generate neg_response
                    # NOTE compare with no space
                    if self.cur_slot[key].replace(' ','') != dst_msg['slot'][key].replace(' ',''):
                        slots_asked.add(key)
                if len(slots_asked) > 0:
                    sent = self.__neg_response(slot=slots_asked,strict=False)
        # check if the DTW intent correct
        if len(intent_asked) > 0 and intent_asked != self.cur_intent:
            sent = self.__neg_response()
        if len(sent) == 0:
            sent = self.__pos_response()
        return sent

    def __question(self, dst_msg, slots_asked, intent_asked):
        sent = ''
        ### check correctness
        if not self.cur_slots_all >= slots_asked: # if DTW ask slots not included in current intent
            sent = self.__neg_response(None)
        else:
            sent = self.sentence_generate(slots_asked)
        return sent

    def __neg_response(self,slot=set([]),strict=True):
        # TODO
        sent = ''
        if slot is not None: # if all the slot are valid
            sent = self.sentence_generate(slots_asked=slot,strict=strict)
        sent = self.prefix_neg_responses[randrange(len(self.prefix_neg_responses))] + sent
        #print 'No! Fuck U!'
        #print sent
        return sent

    def __pos_response(self):
        # TODO
        sent = self.prefix_pos_responses[randrange(len(self.prefix_pos_responses))]
        #print 'Yes! U Asshole!'
        #print sent
        return sent

    def __reward_calculate(self,dst_msg):
        self.cur_reward = TURN_REWARD*self.cur_nb_turn

        ### fill dst_msg with None if the slot not found
        for key in self.cur_slot:
            if key not in dst_msg['slot']:
                dst_msg['slot'][key] = None

        # XXX: remove space
        for key in self.cur_slot:
            if dst_msg['slot'][key] is not None:
                dst_msg['slot'][key] = dst_msg['slot'][key].replace(' ','')
            if self.cur_slot[key] is not None:
                self.cur_slot[key] = self.cur_slot[key].replace(' ','')

        ### check for each slot and intent if all correct
        if dst_msg['intent'] == self.cur_intent and\
            dst_msg['slot']['artist'] == self.cur_slot['artist'] and\
            dst_msg['slot']['track'] == self.cur_slot['track'] and\
            dst_msg['slot']['genre'] == self.cur_slot['genre']:
                self.cur_reward += SUCCESS_REWARD
                self.cur_success = True

       # else:
       #     self.cur_reward -= 1

    def __reset_cur(self):
        self.dialogue_end = True
        # For DST state accuracy computing
        self.cur_state = {'intent':None,'slot':{'track':None,'artist':None, 'genre':None}}
        self.cur_intent = ''
        self.cur_slot = {}
        self.cur_nb_turn = -1
        self.cur_reward = 0.
        self.cur_success = False
        self.cur_slots_all = set()

    def __rand(self, data_lists):
        return data_lists[randrange(len(data_lists))]

    def __load_data(self,template_dir, data_path, genre_path, genre_map_path):
        '''
            Load templates and all the slot data
            Arguments: 
                template_dir: path to the template dir
                data_path: path to the chinese_artist.json
                genre_path: path to the genre.json
            Return: 
                data: dict
                    'artists': list of artists
                    'tracks': list of tracks
                    'track_artist_map': track_artist_map {'t1':'a1','t2':'a2']}
                    'genres': list of genres
                    'intent_template_map': intent to template dictionary
        '''
        ### load file and init
        with open(data_path,'r') as f:
            data_artist = json.load(f)
        with open(genre_path,'r') as f:
            genres=json.load(f)
        with open(genre_map_path,'r') as f:
            genre_map =json.load(f)

        # build genres
        genres = [ key for key in genre_map ] # genre_map: {chinese_genre:english_genre}

        # load artists
        artists = [s for s in data_artist]
        # load tracks and track_artist mappig
        tracks = []
        track_artist_map = {}
        for s in data_artist:
            for a in data_artist[s]:
                for t in data_artist[s][a]:
                    track_artist_map[t] = s
                    tracks.append(t)
        # load intent templates
        intent_template_map = {}
        for i in intents:
            intent_template_map[i] = []
            f = join(template_dir, i+'.csv')
            data_sent = pd.read_csv(f)
            data_sent = data_sent[data_sent.columns[0]].unique()
            intent_template_map[i] = data_sent

        return {'artist':artists, 'tracks':tracks, 'track_artist_map':track_artist_map,\
                'genres':genres, 'intent_template_map':intent_template_map}

def main(args):
    simulator = Simulator(args.template_dir, args.data, args.genre, intents)
    #simulator.set_user_goal(intent='search',artist=u'郭靖', track=u'分手看看', random=True)
    #simulator.print_cur_user_goal()
    #sent = simulator.user_response({'action':'confirm','intent':'search','slot':{'track':u'分手看看2','artist':'fuck'}})
    #print sent

    #print(u':想要幹麼呢？')
    while True:
        if simulator.dialogue_end:
            print ('')
            print(u':請設定user intent和slots:  [\'intent\',\'artist\',\'track\',\'genre\']')
            print('<<<',end='')
            input_goal = sys.stdin.readline()
            try:
                input_goal =  eval(input_goal.decode('utf-8'))
                input_goal = [ g if len(g) > 0 else None for g in input_goal]
                simulator.set_user_goal(intent=input_goal[0], artist=input_goal[1],\
                        track=input_goal[2],genre=input_goal[3])
                print ('>>>' + simulator.user_response({'action':'question'}))
                simulator.print_cur_user_goal()
            except:
                print ('wrong format, should be  [\'intent\',\'artist\',\'track\',\'genre\']')
                continue
        if simulator.cur_set_goal:
            print ('')
            print(u':請輸入DM的action frame: {"action":"?", "intent":"", "slot":{"artist":""}}')
            print('<<<',end='')
            input_frame = sys.stdin.readline()
            try:
                input_frame = eval(input_frame.decode('utf-8'))
                sent_res = simulator.user_response(input_frame)
                print ('>>>' + sent_res)
            except:
                print ('wrong format!!!')
                continue

        if simulator.dialogue_end:
            print ('Dialogue finished!!!')
            simulator.print_cur_user_goal()

def test_DST(args):
    import Dialogue_Manager
    US = Simulator(args.template_dir, args.data, args.genre, args.genre_map, intents)
    US.set_user_goal(random_init=True)
    US.print_cur_user_goal()
    user_sent = US.user_response(start=True)
    
    DM = Dialogue_Manager.Manager(args.nlu_data , args.model, args.genre, verbose=args.verbose)
    c_each_turn =  0.
    nb_turn = 0.
    c_final_turn = 0.
    nb_final_turn = 0.
    count = 0
    while True:
        nb_turn += 1
        action = DM.get_input(user_sent)
        print ('?????',DM.confirmed_state)
        if US.dst_cur_state_check(DM.confirmed_state):
            c_each_turn += 1
        DM.print_current_state()
        user_sent = US.user_response(action)
        print (user_sent)
        print (US.get_reward())
        if DM.dialogue_end:
            count += 1
            US.print_cur_user_goal()
            nb_final_turn += 1
            if US.cur_success:
                c_final_turn += 1
            print("Dialogue System final response:",end=' ')
            print(DM.dialogue_end_sentence)
            print('\nCongratulation!!! You have ended one dialogue successfully\n')
            
            print ('ACC turn:[{:f}]  ACC final:[{}] AVG turns:[{}]'.format(c_each_turn/nb_turn,
                c_final_turn/nb_final_turn, nb_turn/nb_final_turn))
            if count > 10000:
                break

            DM.state_init()
            US.set_user_goal(random_init=True)
            US.print_cur_user_goal()
            user_sent = US.user_response(start=True)
    


if __name__ == '__main__':
    args = opt_parse()
    if args.mode == 'stdin':
        main(args)
    elif args.mode == 'test_dst':
        test_DST(args)
