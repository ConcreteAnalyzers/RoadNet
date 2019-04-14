#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# File: casnet_glc.py
# Author: Yahui Liu <yahui.liu@unitn.it>

import cv2
import tensorflow as tf
import argparse
import numpy as np
from six.moves import zip
import os, glob
import sys
import random

sys.path.insert(0, '../../tensorpack')

from tensorpack import *
from tensorpack.tfutils.symbolic_functions import *
from tensorpack.tfutils.summary import *

SHAPE=512

class Model(ModelDesc):
    def _get_inputs(self):
        return [InputDesc(tf.float32, [None, SHAPE, SHAPE, 3], 'image'),
                InputDesc(tf.int32, [None, SHAPE, SHAPE], 'segment'),
                #InputDesc(tf.int32, [None, SHAPE, SHAPE], 'boundary'),
                InputDesc(tf.int32, [None, SHAPE, SHAPE], 'skeleton')]

    def _build_graph(self, inputs):

        image, segment, skeleton = inputs
        #print image.get_shape().as_list()

        #if get_current_tower_context().is_training:
        #    image = noisy(image)
        #image = image - tf.constant([104, 116, 122], dtype='float32')
        #segment = tf.expand_dims(segment, 3, name='segment4d')
        #boundary = tf.expand_dims(boundary, 3, name='boundary4d')
        #skeleton = tf.expand_dims(skeleton, 3, name='skeleton4d')

        def network1(name, l):
            with argscope(Conv2D, kernel_shape=3, nl=BNReLU), \
                argscope(Deconv2D, kernel_shape=2, stride=2, nl=BNReLU):
                with tf.variable_scope(name):
                    l = Conv2D('conv1_1', l, 32)
                    l = Conv2D('conv1_2', l, 32)
                    l = MaxPooling('pool1', l, 2)

                    l = Conv2D('conv2_1', l, 64)
                    l = Conv2D('conv2_2', l, 64)
                    l = MaxPooling('pool2', l, 2)

                    l = Conv2D('conv3_1', l, 128)
                    l = Conv2D('conv3_2', l, 128)
                    l = Conv2D('conv3_3', l, 128)
                    l = MaxPooling('pool3', l, 2)

                    l = Conv2D('conv4_1', l, 256)
                    l = Conv2D('conv4_2', l, 256)
                    l = Conv2D('conv4_3', l, 256)
                    l = MaxPooling('pool4', l, 2)
                    
                    l = Deconv2D('upsample4', l, 256)
                    l = Conv2D('deconv4_3', l, 256)
                    l = Conv2D('deconv4_2', l, 256)
                    l = Conv2D('deconv4_1', l, 128)
                    
                    l = Deconv2D('upsample3', l, 128)
                    l = Conv2D('deconv3_3', l, 128)
                    l = Conv2D('deconv3_2', l, 128)
                    l = Conv2D('deconv3_1', l, 64)                    
                    
                    l = Deconv2D('upsample2', l, 64)
                    l = Conv2D('deconv2_2', l, 64)
                    l = Conv2D('deconv2_1', l, 32)                    

                    l = Deconv2D('upsample1', l, 32)
                    l = Conv2D('deconv1_2', l, 32)
                    l = Conv2D('deconv1_1', l, 32)
                    l = Conv2D('deconv1', l, 2, nl=tf.identity)
                return l
				
        def network2(name, l):
            with argscope(Conv2D, kernel_shape=3, nl=BNReLU), \
                argscope(Deconv2D, kernel_shape=2, stride=2, nl=BNReLU):
                with tf.variable_scope(name):
                    l = Conv2D('conv1_1', l, 32)
                    l = Conv2D('conv1_2', l, 32)
                    l = MaxPooling('pool1', l, 2)

                    l = Conv2D('conv2_1', l, 64)
                    l = Conv2D('conv2_2', l, 64)
                    l = MaxPooling('pool2', l, 2)

                    l = Conv2D('conv3_1', l, 128)
                    l = Conv2D('conv3_2', l, 128)
                    l = Conv2D('conv3_3', l, 128)
                    l = MaxPooling('pool3', l, 2)
                    
                    l = Deconv2D('upsample3', l, 128)
                    l = Conv2D('deconv3_3', l, 128)
                    l = Conv2D('deconv3_2', l, 128)
                    l = Conv2D('deconv3_1', l, 64)                    
                    
                    l = Deconv2D('upsample2', l, 64)
                    l = Conv2D('deconv2_2', l, 64)
                    l = Conv2D('deconv2_1', l, 32)                    

                    l = Deconv2D('upsample1', l, 32)
                    l = Conv2D('deconv1_2', l, 32)
                    l = Conv2D('deconv1_1', l, 32)
                    l = Conv2D('deconv1', l, 2, nl=tf.identity)
                return l
                    
        def celoss(name, logits, labels, num_classes=2, class_weights=[1.0, 1.0]):
            with tf.name_scope(name):
                label_onehot = tf.one_hot(labels, num_classes, axis=-1)
                weights = label_onehot * class_weights
                weights = tf.reduce_sum(weights, 3)
                return [tf.losses.softmax_cross_entropy(onehot_labels=label_onehot, logits=logits, weights=weights)]

        segment_map = network1('segment', image)
        segment_pred = tf.nn.softmax(segment_map, name='segment-output')
        segment_costs = celoss('segment', segment_map, segment)

        merge_data = tf.concat([image, segment_map], 3)

        skeleton_map = network2('skeleton', merge_data)
        skeleton_pred = tf.nn.softmax(skeleton_map, name='skeleton-output')
        skeleton_costs = celoss('skeleton', skeleton_map, skeleton)


        if get_current_tower_context().is_training:
            wd_w = tf.train.exponential_decay(2e-4, get_global_step_var(),
                                              10000, 0.9, True)
            segment_wd_cost = tf.multiply(wd_w, regularize_cost('segment/.*/W', 
                tf.nn.l2_loss), name='segment_wd_cost')
            segment_costs.append(segment_wd_cost)     
            segment_cost = tf.add_n(segment_costs, name='segment_cost')

            skeleton_wd_cost = tf.multiply(wd_w, regularize_cost('skeleton/.*/W', 
                tf.nn.l2_loss), name='skeleton_wd_cost')
            skeleton_costs.append(skeleton_wd_cost)     
            skeleton_cost = tf.add_n(skeleton_costs, name='skeleton_cost')

            add_moving_summary(segment_cost, skeleton_cost)

            loss = [segment_cost, skeleton_cost]
            
            self.cost = tf.add_n(loss, name='cost')
            add_moving_summary(self.cost)

    def _get_optimizer(self):
        lr = get_scalar_var('learning_rate', 1e-3, summary=True)
        return tf.train.AdamOptimizer(lr, epsilon=1e-3)

def get_data(name):
    isTrain = name == 'train'
    ds = dataset.RoadNetImage2(name, 
        '../../datasets/Guangliang/dataset', shuffle=True)
    print ds.size()
    class CropMultiple16(imgaug.ImageAugmentor):
        def _get_augment_params(self, img):
            newh = img.shape[0] // 16 * 16
            neww = img.shape[1] // 16 * 16
            assert newh > 0 and neww > 0
            diffh = img.shape[0] - newh
            h0 = 0 if diffh == 0 else self.rng.randint(diffh)
            diffw = img.shape[1] - neww
            w0 = 0 if diffw == 0 else self.rng.randint(diffw)
            return (h0, w0, newh, neww)

        def _augment(self, img, param):
            h0, w0, newh, neww = param
            return img[h0:h0 + newh, w0:w0 + neww]

    if isTrain:
        shape_aug = [
            #imgaug.RandomResize(xrange=(0.7, 1.5), yrange=(0.7, 1.5),
            #                    aspect_ratio_thres=0.15),
            #imgaug.RotationAndCropValid(90),
            CropMultiple16(),
            imgaug.Flip(horiz=True),
            #imgaug.Flip(vert=True)
        ]
    else:
        # the original image shape (321x481) in BSDS is not a multiple of 16
        IMAGE_SHAPE = (512, 512)
        shape_aug = [imgaug.CenterCrop(IMAGE_SHAPE)]
    ds = AugmentImageComponents(ds, shape_aug, (0, 1, 2), copy=False)

    def f(m):   # thresholding
        #m = m / 255.0
        m[m >= 0.50] = 1
        m[m < 0.50] = 0
        return m
    ds = MapDataComponent(ds, f, 1)
    ds = MapDataComponent(ds, f, 2)

    if isTrain:
        augmentors = [
            imgaug.Brightness(63, clip=False),
            imgaug.Contrast((0.4, 1.5)),
        ]
        ds = AugmentImageComponent(ds, augmentors, copy=False)
        ds = BatchDataByShape(ds, 1, idx=0)
        ds = PrefetchDataZMQ(ds, 1)
    else:
        ds = BatchData(ds, 1)
    return ds

def view_data():
    ds = RepeatedData(get_data('train'), -1)
    ds.reset_state()
    for ims, edgemaps in ds.get_data():
        for im, edgemap in zip(ims, edgemaps):
            assert im.shape[0] % 16 == 0 and im.shape[1] % 16 == 0, im.shape
            cv2.imshow("im", im / 255.0)
            cv2.waitKey(1000)
            cv2.imshow("edge", edgemap)
            cv2.waitKey(1000)


def get_config():
    logger.auto_set_dir()
    dataset_train = get_data('train')
    steps_per_epoch = 400#dataset_train.size()
    #dataset_val = get_data('val')

    return TrainConfig(
        dataflow=dataset_train,
        callbacks=[
            ModelSaver(),
            ScheduledHyperParamSetter('learning_rate', 
                [(20, 5e-4), (40, 1e-4), (60, 5e-5), (80, 1e-5), (100, 1e-6)]),
            HumanHyperParamSetter('learning_rate')],
        model=Model(),
        steps_per_epoch=steps_per_epoch,
        max_epoch=160,
    )


def run(model_path, image_path, output):
    pred_config = PredictConfig(
        model=Model(),
        session_init=get_model_loader(model_path),
        input_names=['image'],
        output_names=['segment-output', 'boundary-output', 'skeleton-output'])
    predictor = OfflinePredictor(pred_config)

    imgs = glob.glob(os.path.join(image_path, '*.png'))
    import time
    time_consum = []
    for ls in imgs:
        im = cv2.imread(ls)
        assert im is not None
        im = cv2.resize(im, (im.shape[1] // 16 * 16, im.shape[0] // 16 * 16))
        start = time.clock()
        outputs = predictor([[im.astype('float32')]])
        end = time.clock()
        time_consum.append(end-start)
        if output is None:
            for k in range(6):
                pred = outputs[k][0]
                cv2.imwrite("out{}.png".format(
                    '-fused' if k == 5 else str(k + 1)), pred * 255)
        else:
            fname = ls.split('/')[-1]
            fname = fname.split('.')[0]
            mask = cv2.merge([outputs[0][0], outputs[1][0], outputs[2][0]])
            cv2.imwrite(os.path.join(output,fname+'.png'), mask*255, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    print 'image num: {}'.format(len(imgs))
    print 'average infer time (ms): %.3f'%(sum(time_consum)/len(time_consum)) 


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', help='comma separated list of GPU(s) to use.')
    parser.add_argument('--load', help='load model')
    parser.add_argument('--view', help='view dataset', action='store_true')
    parser.add_argument('--run', help='run model on images')
    parser.add_argument('--output', help='fused output filename. default to out-fused.png')
    args = parser.parse_args()
    if args.gpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu

    if args.view:
        view_data()
    elif args.run:
        run(args.load, args.run, args.output)
    else:
        config = get_config()
        if args.load:
            config.session_init = get_model_loader(args.load)
        if args.gpu:
            config.nr_tower = len(args.gpu.split(','))
        SyncMultiGPUTrainer(config).train()