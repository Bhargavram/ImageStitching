import cv2 as cv
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import RectBivariateSpline
import pickle

# docstring based on this https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html


def get_points(image, n=4):
    """Uses ginput to take points as input.
    Args:
        image (numpy.ndarray) : image to take input from.
        n (int) : number of points to take.

    Returns:
        `list` of `tuples` : The `n` points sampled from the image.
    """

    plt.imshow(image)
    points = plt.ginput(n, timeout=-100)
    plt.show()
    plt.close()
    return points

def compute_points_mat(src_points, target_points):
    """
        Transforms a list of tuples - where src_point[i] and
        target_points[i] correspond to the same feature viewed 
        in 2 images - into a format suitable for solving for the 
        homography matrix.

        Args:
            src_points(list of tuples) : points from the first image.
            target_points(list of tuples) : points from the second image. 

        Returns:
            numpy.ndarray: matrix of shape (2 * number of points, 8)
    """


    A = np.empty((2*len(src_points), 8))
    row=0

    for (x_s,y_s),(x_t,y_t) in zip(src_points, target_points):
        
        A[row,0] = A[row+1,3] = x_s
        A[row,1] = A[row+1,4] = y_s
        A[row,2] = A[row+1,5] = 1
        A[row,3:6] = A[row+1,0:3] = 0
        A[row, 6] = -x_s*x_t
        A[row, 7] = -y_s*x_t
        A[row+1, 6] = -x_s*y_t
        A[row+1, 7] = -y_s*y_t
        row+=2
    
    return A 



def compute_homography_mat(src_points, target_points):
    """
        Uses the points in src_points and their corresponding points
        target_points to compute the homography matrix between the 2 images 
        from which the 2 lists where obtained.

        Args:
            src_points(list of tuples) : points from the first image.
            target_points(list of tuples) : points from the second image. 

        Returns:
            numpy.ndarray : matrix of shape (3,3) which is the homgraphy matrix.
    """

    A = compute_points_mat(src_points, target_points)
    b = np.ndarray.flatten(np.array(target_points))
    
    H = np.linalg.lstsq(A, b,None)[0]
    H = np.concatenate([H,[1]])
    H = H.reshape(3,3)
    return H


def transform_points(points, H):
    """
        Given a matrix of points with wach row (u, v) transforms 
        the points using H (the homography matrix).
        Args:
            points (numpy.ndarray) : matrix with each row being a point (u,v)
            H : (numpy.ndarray) :  matrix with shape (3,3) describing a projective transformation in 2D.

        Returns:
            numpy.ndarray : matrix of same shape as points, where mapped_points[i] 
                            is the mapping of points[i] using H.
    
    """


    ones = np.ones((points.shape[0], 1))
    points = np.concatenate([points, ones], 1)

    mapped_points = np.dot(points, H.T)
    mapped_points[:,:-1] /= np.expand_dims(mapped_points[:,-1],1)
    mapped_points = mapped_points[:,:-1]

    return mapped_points


def get_inliers(src_points, target_points, d=1, s=4, N=2000, T=None):
    """
        Uses RANSAC to find out which pairs of points from src_points 
        and target points is an inlier.

        Args:
            src_points(list of tuples) : points from the first image.
            target_points(list of tuples) : points from the second image. 
            d (float) : max distance an inlier can be at relative to the deduced transformation.
            s (int) : number of points to sample at random to solve for H at each iteration.
            N (int) : number of times to run the RANSAC loop.
            T (int) : min number of inliers that need to exist so that we re-solve for the 
                    transformation using the sampled points and the inliers.

        Returns:
            (tuple of numpy.ndarray) : (inliers in image one, their corresponding points in image two)

        Note:
            the number of returned inliers >= s. 

    """
    assert len(src_points) == len(target_points)
    src_points = np.concatenate([np.expand_dims(np.array(p),0) for p in src_points if type(p) != np.ndarray],0)
    target_points = np.concatenate([np.expand_dims(np.array(p),0) for p in target_points if type(p) != np.ndarray],0)
    
    # N = int(np.log10(1-0.99)/np.log10((1-(1-0.4)**s)))

    T  = min(len(src_points), 10)

    samples_indices_history = []

    num_inliers_history = []

    def _get_inlier_indices(indices):
        
        H = compute_homography_mat(src_points[indices], target_points[indices])

        
        mapped_points = transform_points(src_points, H)

        dist = np.linalg.norm(mapped_points - target_points, axis=1)
        inlier_indices = np.where(dist <= d)[0]
        return inlier_indices
    

    for _ in range(N):
        indices = np.random.choice(len(src_points), s, replace=False)
        
        inlier_indices = _get_inlier_indices(indices)
        samples_indices_history.append(inlier_indices)
        num_inliers_history.append(len(inlier_indices))

        if num_inliers_history[-1] >= T:
            inlier_indices = _get_inlier_indices(inlier_indices)
            samples_indices_history.append(inlier_indices)
            num_inliers_history.append(len(inlier_indices))
            

    samples_indices_history = np.array(samples_indices_history)
    num_inliers_history = np.array(num_inliers_history)
    best_indices = samples_indices_history[np.argmax(num_inliers_history)]
    return src_points[best_indices], target_points[best_indices]



def transform_grid(u_range, v_range, H):
    """
        Generates a grid of with u values belonging to u_range and v values 
        belonging to v_range and transforms it using H.
        
        Args:
            u_range (numpy.ndarray): vector of length (N)
            v_range (numpy.ndarray): vector of length (M)
            H (numpy.ndarray) : matrix of shape (3,3) used to project the grid of points.
        
        Returns:
            (tuple of numpy.ndarray) : 
                first element: points of the grid layed out in a matrix with each row representing
                                a point (u, v)
                second element: a matrix of the same shape as the first element where each row 
                                represents the corresponding mapped point (u',v') using H.
    """



    grid_u, grid_v = np.meshgrid( u_range, v_range )

    u_flat = np.expand_dims(np.ndarray.flatten(grid_u), 1)
    v_flat = np.expand_dims(np.ndarray.flatten(grid_v), 1)
    points = np.concatenate([u_flat, v_flat],1)
    
    return points, transform_points(points, H)


def warp_image(image, H):

    """Warps an image using the homography matrix H.

    Args:
        image (numpy.ndarray): image to be warpped.
        H (numpy.ndarray) : Homography matrix used to warp the image.
    
    Returns:
        (tuple of numpy.ndarray, int, int):
            first element: the warpped images.
            second element: the minimum u corrdinate in corrdinate space not image space
                            this means this could be a negative number, in other words 
                            this is the amount of translation in the u diraction.

            third element: minimum v corrdcinate i.e. the translation in v direction.
    """

    H_inv = np.linalg.inv(H) 
    H_inv = H_inv / H_inv[2,2]
    # u == x
    # v == y
    

    orig_u_range = np.arange(image.shape[1])
    orig_v_range = np.arange(image.shape[0])

    _, transformed_image, = transform_grid(orig_u_range, orig_v_range, H)
    
    min_u=int(np.min(transformed_image[:,0]))
    max_u=int(np.max(transformed_image[:,0]))
    min_v=int(np.min(transformed_image[:,1]))
    max_v=int(np.max(transformed_image[:,1]))

    mapped_u_range = np.arange(min_u, max_u)
    mapped_v_range = np.arange(min_v, max_v)
    
    

    target_image = np.zeros((max_v-min_v, max_u-min_u,3))


    transformed_points, inv_transformed_image = transform_grid(mapped_u_range, mapped_v_range, H_inv)

    def fill_channel(target, channel, batch_size=64):
        I_cont = RectBivariateSpline(orig_v_range, orig_u_range, image[:,:,channel])

        n_iters =int( len(inv_transformed_image) / batch_size )
        
        for i in range(n_iters + 1):
            start = i * batch_size
            end = (i+1) * batch_size
            
            mapped_u_batch = inv_transformed_image[start:end, 0].ravel()
            mapped_v_batch = inv_transformed_image[start:end, 1].ravel()
            
            u_batch = transformed_points[start:end, 0].ravel()
            v_batch = transformed_points[start:end, 1].ravel()

            target[v_batch-min_v, u_batch-min_u, channel] = I_cont(mapped_v_batch, mapped_u_batch, grid=False)

    fill_channel(target_image, 0)
    fill_channel(target_image, 1)
    fill_channel(target_image, 2)

    return target_image, min_u, min_v
                
def read_image(path):
    # img = cv.imread(path)
    img = cv.imread(path,1)
    return img


def automatic_intrest_points_detector(image1, image2, N=75):
    """
    This function get key point from two images instead of doing it manullay


    Args:
        image1: first image to get key points from
        image2: second images to get key points from
        N: Number of points to be detected 

    Returns:
        Two lists of detected interest points from the two images
    """
    # ORB: An efficient alternative to SIFT or SURF
    orb = cv.ORB_create() 
    
    # get key points and descriptors from the 2 images
    kps1, descs1 = orb.detectAndCompute(image1, None)
    kps2, descs2 = orb.detectAndCompute(image2, None)
    
    # brute force matcher
    bf = cv.BFMatcher(cv.NORM_HAMMING, crossCheck=True)
    matches = bf.match(descs1, descs2)
    matches = sorted(matches, key=lambda x:x.distance)
    list_kps1 = [kps1[mat.queryIdx].pt for mat in matches[:N]] 
    list_kps2 = [kps2[mat.trainIdx].pt for mat in matches[:N]]

    return list_kps1, list_kps2


def stitch_2_images(path_1, path_2, correspondance_points=5, save=True, load=True, SIFT=False):
    """
    stitches 2 images.

    path_1(str) : path to first image
    path_2(str) : path to second image
    correspondance points(int) : number of points to take from each image for pixel matching.
    save (bool) : weather to save the sampled points in a pickel file.
    load (boo) : weather to load the points from a pickel file with the same name as the images.
    SIFT (bool) : weather to use SIFT features to match interest points or input the points manually.
    
    Returns:
        (numpy.ndarray) : matrix of shape ((warpped_image_1.shape[0] + image_2.shape[0],
                                            warpped_image_1.shape[1] + image_2.shape[1], 3))
                         which is the stitched images.
    """


    image_1 = read_image(path_1)
    image_2 = read_image(path_2)

    image_1_name = path_1.split('/')[-1].split('.')[0]
    image_2_name = path_2.split('/')[-1].split('.')[0]
    
    if load:
        with open(f'{image_1_name}.pkl', 'rb') as f:
            image_1_points = pickle.load(f)

        with open(f'{image_2_name}.pkl', 'rb') as f:
            image_2_points = pickle.load(f)

    else:
        if SIFT:
            image_1_points, image_2_points = automatic_intrest_points_detector(image_1, image_2, correspondance_points)
            # fig, axs = plt.subplots(1,2)
            # i_1 = np.array(image_1_points)
            # i_2 = np.array(image_2_points)
            # axs[0].imshow(image_1)
            # axs[0].scatter(i_1[:,0], i_1[:,1])
            # axs[1].imshow(image_2)
            # axs[1].scatter(i_2[:,0], i_2[:,1])
            # plt.show()

        else:
            image_1_points = get_points(image_1, correspondance_points)
            image_2_points = get_points(image_2, correspondance_points)
    
    if save:
        with open(f'{image_1_name}.pkl', 'wb+') as f:
            pickle.dump(image_1_points,f)

        with open(f'{image_2_name}.pkl', 'wb+') as f:
            pickle.dump(image_2_points, f)

    # convert bgr to rgb then scale image to range [0,1)
    image_1 = image_1[...,::-1]/255
    image_2 = image_2[...,::-1]/255

    inlier_src, inlier_target = get_inliers(image_1_points, image_2_points)

    # fig, axs = plt.subplots(1,2)
    # axs[0].imshow(image_1)
    # axs[0].scatter(inlier_src[:,0], inlier_src[:,1])
    # axs[1].imshow(image_2)
    # axs[1].scatter(inlier_target[:,0], inlier_target[:,1])
    # plt.show()



    H = compute_homography_mat(inlier_src, inlier_target)



    warpped_image_1, min_u, min_v = warp_image(image_1, H)

    res = np.zeros((warpped_image_1.shape[0] + image_2.shape[0],
                    warpped_image_1.shape[1] + image_2.shape[1], 3))

    shift_u_1 = min_u if min_u>0 else 0
    shift_v_1 = min_v if min_v>0 else 0

    res[shift_v_1:warpped_image_1.shape[0]+shift_v_1, shift_u_1:warpped_image_1.shape[1]+shift_u_1, :] = warpped_image_1

    shift_u_2 = -min_u if min_u<0 else 0
    shift_v_2 = -min_v if min_v<0 else 0
    res[shift_v_2:image_2.shape[0] + shift_v_2, shift_u_2:image_2.shape[1] + shift_u_2, :] = image_2

    res = res[0:np.maximum(image_1.shape[0], image_2.shape[0])+200,
              0:np.maximum(image_1.shape[1], image_2.shape[1])+700]
    return res

def stitch_N_images(paths):
    """
    stitches N images.

    paths : paths to N images with know order
    
    Returns:
        (numpy.ndarray) : matrix of shape ((warpped_image_1.shape[0] + image_2.shape[0],
                                            warpped_image_1.shape[1] + image_2.shape[1], 3))
                         which is the stitched images.
    """
    N = len(paths)
    for i in range(N-1):
        res = stitch_2_images(paths[i+1], paths[i] , 100, load=False, save=False, SIFT=True)
        name = 'images'+str(1)+str(2)+'.png'
        paths[i] = name
        plt.imsave(name, res)
    return res



# paths = ['mount1.png', 'mount2.png', 'mount3.png'] 
paths = ['1.png', '2.png', '3.png', '4.png'] 
# paths = ['b1.png', 'b2.png']

res = stitch_N_images(paths)
plt.imshow(res)
plt.show()





# def main():
#     building_1 = read_image('b1.png')
#     building_2 = read_image('b2.png')

#     building_1_points, building_2_points = automatic_intrest_points_detector(building_1, building_2)
#     plt.figure(1)
#     plt.imshow(building_1)
#     for point in building_1_points:
#         plt.scatter(point[0], point[1], c='red')
    
#     H = compute_homography_mat(building_1_points, building_2_points)
#     plt.figure(2)
#     plt.imshow(building_2)
#     mapped_points = []
#     for point in building_1_points:
#         mapped_point1 = transform_point(point, H)
#         # mapped_point2 = transform_point([point[0] + 500, point[1] + 500], H)
#         # mapped_point3 = transform_point([point[0] + 100, point[1] + 100], H)

#         mapped_points.append(mapped_points)
        
#         plt.scatter(mapped_point1[0], mapped_point1[1], c='red')
#         # plt.scatter(mapped_point2[0], mapped_point2[1], c='blue')
#         # plt.scatter(mapped_point3[0], mapped_point3[1], c='yellow')

    
#     plt.show()

# main()

#     try:
#         with open('b1.pkl', 'rb') as f:
#             building_1_points = pickle.load(f)
        
#         with open('b2.pkl', 'rb') as f:
#             building_2_points = pickle.load(f)
        
#     except:
#         building_1_points = get_points(building_1,5)
#         building_2_points = get_points(building_2,5)


#         with open('b1.pkl','wb+') as f:
#             pickle.dump(building_1_points,f)

#         with open('b2.pkl','wb+') as f:
#             pickle.dump(building_2_points,f)
            

   
#     H = compute_homography_mat(building_1_points, building_2_points)
#     # H = np.eye(3) * 1.5
#     # H[2,2]=1


#     plt.imshow(building_2)
#     mapped_points = []
#     for point in building_1_points:
#         mapped_point1 = transform_point(point, H)
#         mapped_point2 = transform_point([point[0] + 500, point[1] + 500], H)
#         mapped_point3 = transform_point([point[0] + 100, point[1] + 100], H)

#         mapped_points.append(mapped_points)
        
#         plt.scatter(mapped_point1[0], mapped_point1[1], c='red')
#         plt.scatter(mapped_point2[0], mapped_point2[1], c='blue')
#         plt.scatter(mapped_point3[0], mapped_point3[1], c='yellow')

    
#     plt.show()


#     # plt.imshow(building_1)
#     # H_inv = np.linalg.inv(H)

#     # b1_points = []

#     # for point in mapped_points + [[0,0]]:
#     #     b1_point = transform_point(point, H_inv/H_inv[2,2])
#     #     b1_points.append(b1_point)
#     #     plt.scatter(b1_point[0], b1_point[1], c='yellow')

#     # plt.show()

#     try:
#         with open('warpped.pkl', 'rb') as f:
#             warpped_building_1, min_u, min_v = pickle.load(f)
    
#     except:
#         warpped_building_1, min_u, min_v = warp_image(building_1, H)
#         with open('warpped.pkl', 'wb+') as f:
#             pickle.dump((warpped_building_1, min_u, min_v), f)
        

#     res = np.zeros((warpped_building_1.shape[0] + building_2.shape[0],
#                     warpped_building_1.shape[1] + building_2.shape[1], 3))



#     res[:warpped_building_1.shape[0], :warpped_building_1.shape[1], :] = warpped_building_1

#     res[-min_v:-min_v + building_2.shape[0], -min_u:-min_u + building_2.shape[1], :] = building_2
    
#     # res[:, int(pivot[0]):, :]  = building_2[:, mapped_points[0][0]:, :]



#     plt.imshow( res )

#     plt.show()


    
    





# main()

# H = np.array([[ 1.96266782e-01 , -1.98196535e+00 , 4.81034471e+02],
#  [ 1.07510522e-01 , -1.23659214e+00 , 3.14197533e+02],
#  [ 3.24089376e-04 , -3.88242171e-03 , 1.00000000e+00]])
    
# # x = np.array((814.9165742210662, 317.62283151311124))
# # x_hom = np.array((814.9165742210662, 317.62283151311124,1))
# x_hom = np.array([0,0,1])
# scaler = 1/(H[2,0]*x_hom[0] + H[2,1]*x_hom[1] + 1)
# x_t_hom = scaler * H.dot(x_hom)
# print(x_t_hom)
# H_inv = np.linalg.inv(H)
# H_inv = H_inv / H_inv[2,2]
# scaler = 1/(H_inv[2,0]*x_t_hom[0] + H_inv[2,1]*x_t_hom[1] + 1)
# print(H_inv)
# print( scaler * H_inv.dot(x_t_hom))










