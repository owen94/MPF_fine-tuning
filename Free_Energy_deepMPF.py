'''
This is the deep MPF. We implement the MPF-EM algorithm here for training RBMs.
Step 1: Binarize the input data, initialize weight and bias
Step 2: Feedforward and sampling to get the hidden activations
Step 3: Train the MPF to find the better weights and bias
Step 4: repeat Step 2 and 3 until weight converge.
Step 5: Sanity check, conduct generating tasks
'''


from dmpf_optimizer import *
from free_energy_dmpf import *
from sklearn import preprocessing
import numpy as np
import gzip
import timeit, pickle, sys, math
import theano
import theano.tensor as T
import Image
import copy
import os
from free_energy_dmpf import *

from utils import tile_raster_images

def mpf_em(dataset,hidden_units,dynamic=False):


    ################################################################
    ################## Loading the Data        #####################
    ################################################################

    if dataset is None:
        dataset = 'mnist.pkl.gz'
        f = gzip.open(dataset, 'rb')
        train_set, valid_set, test_set = pickle.load(f,encoding="bytes")
        f.close()

    else:
        f = gzip.open(dataset, 'rb')
        train_set, valid_set, test_set = pickle.load(dataset,encoding="bytes")
        f.close()


    binarizer = preprocessing.Binarizer(threshold=0.5)
    data =  binarizer.transform(train_set[0][0:10000,:])
    print(data.shape)
    # k = data[:1,:]
    # print(k)
    # print(train_set[0][:1,:])

    #data = np.load('gibbs_samples.npy')


    ################################################################
    ##################  Initialize Parameters  #####################
    ################################################################

    #visible_units = train_set[0].shape[1]
    visible_units = data.shape[1]

    num_units = visible_units + hidden_units

    # np.save('rbm_W.npy',W)
    # bias can be intialized in the MPF_optimizer class

    ################################################################
    ##################  Train MPF              #####################
    ################################################################

    # In one round, we feedfoward the and get the samples,
    # Compute the probability of each data samples,
    # call the minimum probability flow objective function

    epsilon = 0.05
    learning_rate = 0.05
    index = T.lscalar()    # index to a mini batch
    x = T.matrix('x')
    batch_sz = 20

    mpf_optimizer = free_energy_dmpf_optimizer(epsilon=epsilon, visible_units= visible_units, hidden_units= hidden_units,
                 input = x,batch_sz =batch_sz)

    n_train_batches = data.shape[0]//batch_sz

    data  = theano.shared(value=np.asarray(data, dtype=theano.config.floatX),
                                  name = 'train',borrow = True)

    cost,updates = mpf_optimizer.get_cost_updates(learning_rate= learning_rate)

    train_mpf = theano.function(
        [index],
        cost,
        updates=updates,
        givens={
            x: data[index * batch_sz: (index + 1) * batch_sz],
        },
        #on_unused_input='warn',
    )

    training_epochs = 50

    start_time = timeit.default_timer()

    mean_epoch_error = []

    for epoch in range(training_epochs):

        # go through the training set
        mean_cost = []
        mean_batch_error = []
        norm_batch_error = []


        for batch_index in range(n_train_batches):
            # weight = mpf_optimizer.W.get_value(borrow = True)
            # bia = mpf_optimizer.b.get_value(borrow = True)
            mean_cost += [train_mpf(batch_index)]

        mean_epoch_error += [np.mean(mean_cost)]
        print('The cost for dmpf in epoch %d is %f'% (epoch,np.mean(mean_cost)))
            # print(mean_cost)
            # error_W = np.sum((W_init - mpf_optimizer.W.get_value(borrow=True))**2)
            # error_bias = np.sum((bia - mpf_optimizer.b.get_value(borrow= True))**2)
            #
            # #print(error_bias)
            #
            # error = error_bias + error_W
            #
            # mean_batch_error += [error_W/(2*hidden_units*visible_units)]

            # norm_batch_error += [np.sum(( W/(np.sum(W**2)) -
            # mpf_optimizer.W.get_value(borrow=True)/(np.sum(mpf_optimizer.W.get_value(borrow=True)**2)) )**2 )]


        if epoch % 5 == 0 :
            image = Image.fromarray(
            tile_raster_images(
                X=(mpf_optimizer.W.get_value(borrow = True)).T,
                img_shape=(28, 28),
                tile_shape=(15, 15),
                tile_spacing=(1, 1)
            )
            )
            np.save('W_epoch_'+str(epoch)+'.npy',
                    (mpf_optimizer.W.get_value(borrow = True)[:visible_units,visible_units:]).T)
            image.show()
            image.save('filters_at_epoch_%i.png' % epoch)

        # if (epoch +1) % 100 == 0:
        #     learning_rate = learning_rate / 10
        #mean_epoch_error += [np.mean((mean_batch_error))]

        # print(mean_cost)

        # print(mean_epoch_error[-1])
        #
        # if epoch > 2 and mean_epoch_error[-1] > mean_epoch_error[-2]:
        #     print('Ending epoch is %d .' % epoch)
        #     break
        # norm_epoch_error += [np.mean(np.sqrt(norm_batch_error))]
        #
        # print('Training epoch %d, cost is %f' % (epoch, np.mean(mean_cost) ) )

    end_time = timeit.default_timer()

    pretraining_time = (end_time - start_time)

    print ('Training took %f minutes' % (pretraining_time / 60.))


    ################################################################
    ##################  Sampling               #####################
    ################################################################

    n_chains = 20
    n_samples = 10
    rng = np.random.RandomState(123)
    test_set_x = test_set[0]
    number_of_test_samples = test_set_x.shape[0]
    test_set_x = theano.shared( value = np.asarray(test_set_x,
                                                   dtype=theano.config.floatX),name = 'test', borrow = True)

    # pick random test examples, with which to initialize the persistent chain
    test_idx = rng.randint(number_of_test_samples - n_chains)
    persistent_vis_chain = theano.shared(
        np.asarray(
            test_set_x.get_value(borrow=True)[test_idx:test_idx + n_chains],
            dtype=theano.config.floatX
        )
    )
    # end-snippet-6 start-snippet-7
    plot_every = 1000
    # define one step of Gibbs sampling (mf = mean-field) define a
    # function that does `plot_every` steps before returning the
    # sample for plotting
    (
        [
            presig_hids,
            hid_mfs,
            hid_samples,
            presig_vis,
            vis_mfs,
            vis_samples
        ],
        updates
    ) = theano.scan(
        mpf_optimizer.gibbs_vhv,
        outputs_info=[None, None, None, None, None, persistent_vis_chain],
        n_steps=plot_every
    )

    # add to updates the shared variable that takes care of our persistent
    # chain :.
    updates.update({persistent_vis_chain: vis_samples[-1]})
    # construct the function that implements our persistent chain.
    # we generate the "mean field" activations for plotting and the actual
    # samples for reinitializing the state of our persistent chain
    sample_fn = theano.function(
        [],
        [
            vis_mfs[-1],
            vis_samples[-1]
        ],
        updates=updates,
        name='sample_fn'
    )

    # create a space to store the image for plotting ( we need to leave
    # room for the tile_spacing as well)
    image_data = np.zeros(
        (29 * n_samples + 1, 29 * n_chains - 1),
        dtype='uint8'
    )
    for idx in range(n_samples):
        # generate `plot_every` intermediate samples that we discard,
        # because successive samples in the chain are too correlated
        vis_mf, vis_sample = sample_fn()
        print(' ... plotting sample ', idx)
        image_data[29 * idx:29 * idx + 28, :] = tile_raster_images(
            X=vis_mf,
            img_shape=(28, 28),
            tile_shape=(1, n_chains),
            tile_spacing=(1, 1)
        )

    # construct image
    image = Image.fromarray(image_data)
    image.save('samples.png')
    # end-snippet-7
    os.chdir('../')

    return mpf_optimizer.W.get_value(borrow = True), mpf_optimizer.b.get_value(borrow = True)


if __name__ == '__main__':

    W, b = mpf_em(hidden_units=300, dataset= None)


    test_image = tile_raster_images(
        X=W.T,
        img_shape=(28, 28),
        tile_shape=(10, 10),
        tile_spacing=(1, 1)
    )
    print(test_image.shape)
    image = Image.fromarray(test_image)

    image.save('filters.png')






