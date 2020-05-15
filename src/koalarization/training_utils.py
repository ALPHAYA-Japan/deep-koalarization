import pickle
import time
from os.path import join

import matplotlib
import numpy as np
import tensorflow as tf
from skimage import color

from .dataset.labels import inception_labels
from .dataset.shared import maybe_create_folder
from .dataset.tfrecords import LabImageRecordReader

matplotlib.use('Agg')
matplotlib.rcParams['figure.figsize'] = (10.0, 4.0)
import matplotlib.pyplot as plt


def loss_with_metrics(img_ab_out, img_ab_true, name=''):
    # Loss is mean square erros
    cost = tf.reduce_mean(
        tf.squared_difference(img_ab_out, img_ab_true), name="mse")
    # Metrics for tensorboard
    summary = tf.summary.scalar('cost ' + name, cost)
    return cost, summary


def training_pipeline(col, learning_rate, batch_size, dir_tfrecord):
    # Set up training (input queues, graph, optimizer)
    irr = LabImageRecordReader('lab_images_*.tfrecord', dir_tfrecord)
    read_batched_examples = irr.read_batch(batch_size, shuffle=True)
    # read_batched_examples = irr.read_one()
    imgs_l = read_batched_examples['image_l']
    imgs_true_ab = read_batched_examples['image_ab']
    imgs_emb = read_batched_examples['image_embedding']
    imgs_ab = col.build(imgs_l, imgs_emb)
    cost, summary = loss_with_metrics(imgs_ab, imgs_true_ab, 'training')
    global_step = tf.Variable(0, name='global_step', trainable=False)
    optimizer = tf.train.AdamOptimizer(learning_rate).minimize(
        cost, global_step=global_step)
    return {
        'global_step': global_step,
        'optimizer': optimizer,
        'cost': cost,
        'summary': summary
    }#, irr, read_batched_examples


def evaluation_pipeline(col, number_of_images, dir_tfrecord):
    # Set up validation (input queues, graph)
    irr = LabImageRecordReader('val_lab_images_*.tfrecord', dir_tfrecord)
    read_batched_examples = irr.read_batch(number_of_images, shuffle=False)
    imgs_l_val = read_batched_examples['image_l']
    imgs_true_ab_val = read_batched_examples['image_ab']
    imgs_emb_val = read_batched_examples['image_embedding']
    imgs_ab_val = col.build(imgs_l_val, imgs_emb_val)
    cost, summary = loss_with_metrics(imgs_ab_val, imgs_true_ab_val,
                                      'validation')
    return {
        'imgs_l': imgs_l_val,
        'imgs_ab': imgs_ab_val,
        'imgs_true_ab': imgs_true_ab_val,
        'imgs_emb': imgs_emb_val,
        'cost': cost,
        'summary': summary
    }


class Logger(object):
    def __init__(self, path):
        self.f = open(path, 'a')

    def write(self, text):
        self.f.write(f'[{time.strftime("%c")}] {text}\n')
        self.f.flush()


def metrics_system(sess, dir_metrics):
    # Merge all the summaries and set up the writers
    train_writer = tf.summary.FileWriter(dir_metrics, sess.graph)
    return train_writer


def checkpointing_system(dir_checkpoints):
    # Add ops to save and restore all the variables.
    saver = tf.train.Saver()
    latest_checkpoint = tf.train.latest_checkpoint(dir_checkpoints)
    checkpoint_paths = join(dir_checkpoints, 'weights')
    return saver, checkpoint_paths, latest_checkpoint


def plot_evaluation(res, global_step, dir_images):
    maybe_create_folder(dir_images)
    for k in range(len(res['imgs_l'])):
        img_gray = l_to_rgb(res['imgs_l'][k][:, :, 0])
        img_output = lab_to_rgb(res['imgs_l'][k][:, :, 0],
                                res['imgs_ab'][k])
        img_true = lab_to_rgb(res['imgs_l'][k][:, :, 0],
                              res['imgs_true_ab'][k])
        top_5 = np.argsort(res['imgs_emb'][k])[-5:]
        try:
            top_5 = ' / '.join(inception_labels[i] for i in top_5)
        except:
            ptop_5 = str(top_5)

        plt.subplot(1, 3, 1)
        plt.imshow(img_gray)
        plt.title('Input (grayscale)')
        plt.axis('off')
        plt.subplot(1, 3, 2)
        plt.imshow(img_output)
        plt.title('Network output')
        plt.axis('off')
        plt.subplot(1, 3, 3)
        plt.imshow(img_true)
        plt.title('Target (original)')
        plt.axis('off')
        plt.suptitle(top_5, fontsize=7)

        plt.savefig(join(dir_images, f'{global_step}_{k}.png'))
        plt.clf()
        plt.close()


def l_to_rgb(img_l):
    """
    Convert a numpy array (l channel) into an rgb image
    :param img_l:
    :return:
    """
    lab = np.squeeze(255 * (img_l + 1) / 2)
    return color.gray2rgb(lab) / 255


def lab_to_rgb(img_l, img_ab):
    """
    Convert a pair of numpy arrays (l channel and ab channels) into an rgb image
    :param img_l:
    :return:
    """
    lab = np.empty([*img_l.shape[0:2], 3])
    lab[:, :, 0] = np.squeeze(((img_l + 1) * 50))
    lab[:, :, 1:] = img_ab * 127
    return color.lab2rgb(lab)
