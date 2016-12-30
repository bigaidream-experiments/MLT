import tensorflow as tf
import tensorlayer as tl
from tensorlayer.layers import set_keep
import numpy as np
import resnet_model
import argparse

parser = argparse.ArgumentParser(description='Define parameters.')

parser.add_argument('--n_epoch', type=int, default=10)
parser.add_argument('--n_batch', type=int, default=64)
parser.add_argument('--n_img_row', type=int, default=28)
parser.add_argument('--n_img_col', type=int, default=28)
parser.add_argument('--n_img_channels', type=int, default=3)
parser.add_argument('--n_classes', type=int, default=100)
parser.add_argument('--lr', type=float, default=0.1)
parser.add_argument('--n_resid_units', type=int, default=5)
parser.add_argument('--lr_schedule', type=int, default=60)
parser.add_argument('--lr_factor', type=float, default=0.1)

args = parser.parse_args()


def unpickle(file):
    import cPickle
    fo = open(file, 'rb')
    dict = cPickle.load(fo)
    fo.close()
    return dict


def distort_img(x):
    x = tl.prepro.flip_axis(x, axis=1, is_random=True)
    x = tl.prepro.crop(x, wrg=28, hrg=28, is_random=True)
    return x


class CNNEnv:
    def __init__(self):

        # The data, shuffled and split between train and test sets
        #self.x_train, self.y_train, self.x_test, self.y_test = tl.files.load_cifar10_dataset(shape=(-1, 32, 32, 3), plotable=False)

	train_data = unpickle('./cifar-100-python/train')
	train_data_num = len(train_data['fine_labels'])
	self.x_train = np.array(train_data['data'],dtype=np.float32).reshape((train_data_num,3,32,32)).transpose((0,2,3,1))
	self.y_train = np.array(train_data['fine_labels'],dtype=np.int64)
	test_data = unpickle('./cifar-100-python/test')
	test_data_num = len(test_data['fine_labels'])
	self.x_test = np.array(test_data['data'],dtype=np.float32).reshape((test_data_num,3,32,32)).transpose((0,2,3,1))
	self.y_test = np.array(test_data['fine_labels'],dtype=np.int64)
        #self.x_train = tl.prepro.threading_data(self.x_train[:], distort_img)
        #self.x_test = tl.prepro.threading_data(self.x_test[:], distort_img)



        # Reorder dimensions for tensorflow
        self.mean = np.mean(self.x_train, axis=0, keepdims=True)
        self.std = np.std(self.x_train)
        self.x_train = (self.x_train - self.mean) / self.std
        self.x_test = (self.x_test - self.mean) / self.std

        print('x_train shape:', self.x_train.shape)
        print('x_test shape:', self.x_test.shape)
        print('y_train shape:', self.y_train.shape)
        print('y_test shape:', self.y_test.shape)

        # For generator
        self.num_examples = self.x_train.shape[0]
        self.index_in_epoch = 0
        self.epochs_completed = 0

        # Basic info
        self.batch_num = args.n_batch
        self.num_epoch = args.n_epoch
        self.img_row = args.n_img_row
        self.img_col = args.n_img_col
        self.img_channels = args.n_img_channels
        self.nb_classes = args.n_classes
        self.num_iter = self.x_train.shape[0] / self.batch_num  # per epoch

    def next_batch(self, batch_size):
        """Return the next `batch_size` examples from this data set."""
        self.batch_size = batch_size

        start = self.index_in_epoch
        self.index_in_epoch += self.batch_size

        if self.index_in_epoch > self.num_examples:
            # Finished epoch
            self.epochs_completed += 1
            # Shuffle the data
            perm = np.arange(self.num_examples)
            np.random.shuffle(perm)
            self.x_train = self.x_train[perm]
            self.y_train = self.y_train[perm]

            # Start next epoch
            start = 0
            self.index_in_epoch = self.batch_size
            assert self.batch_size <= self.num_examples
        end = self.index_in_epoch
        return self.x_train[start:end], self.y_train[start:end]

    def train(self, hps):
        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        sess = tf.InteractiveSession(config=config)

        img = tf.placeholder(tf.float32, shape=[self.batch_num, 28, 28, 3])
        labels = tf.placeholder(tf.int32, shape=[self.batch_num, ])

        model = resnet_model.ResNet(hps, img, labels, 'train')
        model.build_graph()

        merged = model.summaries
        train_writer = tf.summary.FileWriter("/tmp/train_log", sess.graph)

        sess.run(tf.global_variables_initializer())
        print('Done initializing variables')
        print('Running model...')

        # Set default learning rate for scheduling
        lr = args.lr

        for j in range(self.num_epoch):
            print('Epoch {}'.format(j+1))

            # Decrease learning rate every args.lr_schedule epoch
            # By args.lr_factor
            if (j + 1) % args.lr_schedule == 0:
                lr *= args.lr_factor

            for i in range(self.num_iter):
                batch = self.next_batch(self.batch_num)
                feed_dict = {img: batch[0],
                             labels: batch[1],
                             model.lrn_rate: lr}
                _, l, ac, summary, lr = sess.run([model.train_op, model.cost, model.acc, merged, model.lrn_rate], feed_dict=feed_dict)
                train_writer.add_summary(summary, i)
                #
                if i % 200 == 0:
                    print('step', i+1)
                    print('Training loss', l)
                    print('Training accuracy', ac)
                    print('Learning rate', lr)

            print('Running evaluation...')

            test_loss, test_acc, n_batch = 0, 0, 0
            for batch in tl.iterate.minibatches(inputs=self.x_test,
                                                targets=self.y_test,
                                                batch_size=self.batch_num,
                                                shuffle=False):
                feed_dict_eval = {img: batch[0], labels: batch[1]}

                loss, ac = sess.run([model.cost, model.acc], feed_dict=feed_dict_eval)
                test_loss += loss
                test_acc += ac
                n_batch += 1

            tot_test_loss = test_loss / n_batch
            tot_test_acc = test_acc / n_batch

            print('   Test loss: {}'.format(tot_test_loss))
            print('   Test accuracy: {}'.format(tot_test_acc))

        print('Completed training and evaluation.')

run = CNNEnv()

hps = resnet_model.HParams(batch_size=run.batch_num,
                           num_classes=run.nb_classes,
                           min_lrn_rate=0.0001,
                           lrn_rate=args.lr,
                           num_residual_units=args.n_resid_units,
                           use_bottleneck=False,
                           weight_decay_rate=0.0002,
                           relu_leakiness=0.1,
                           optimizer='mom')

run.train(hps)
